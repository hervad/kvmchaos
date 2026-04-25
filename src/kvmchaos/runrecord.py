"""Per-run JSON record writer for kvmchaos.

Writes one JSON file per inject invocation to a XDG-compliant directory.
Each file contains the full lifecycle of a single inject run: fault, VM,
URI, timestamps, per-step outcomes, and overall result.
"""

from __future__ import annotations

import json
import os
import pwd
import tempfile
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "default_runs_dir",
    "filter_records",
    "load_record",
    "resolve_id",
    "write_run_record",
]


def default_runs_dir() -> Path:
    """Return the XDG-compliant default directory for per-run JSON records.

    When running under ``sudo``, ``SUDO_USER`` is set to the invoking user's
    name. In that case the record is written to that user's state directory
    rather than root's, so the audit trail stays with the operator.

    Returns:
        Path under ``$XDG_STATE_HOME/kvmchaos/runs/``, defaulting to
        ``~<user>/.local/state/kvmchaos/runs/``. Falls back to the current
        user's home if ``SUDO_USER`` cannot be resolved.
    """
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg) / "kvmchaos" / "runs"
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        try:
            home = Path(pwd.getpwnam(sudo_user).pw_dir)
            return home / ".local" / "state" / "kvmchaos" / "runs"
        except KeyError:
            pass
    return Path.home() / ".local" / "state" / "kvmchaos" / "runs"


def filter_records(
    records: list[dict[str, object]],
    *,
    since: datetime | None = None,
    fault: str | None = None,
    outcome: str | None = None,
    vm: str | None = None,
) -> list[dict[str, object]]:
    """Return records matching every non-None filter.

    Filters compose via AND. A record is kept only if it passes every
    non-None condition.

    Args:
        records: Run records to filter.
        since: Drop records whose ``started_at`` is before this datetime
            (inclusive). Records missing ``started_at`` are dropped. A
            non-ISO ``started_at`` raises ``ValueError`` (fail-fast, the
            record writer never produces one so the input is corrupt).
        fault: Exact match on the ``fault`` field.
        outcome: Exact match on the ``outcome`` field.
        vm: Exact match on the ``vm`` field.

    Returns:
        A new list containing only matching records; original order preserved.

    Raises:
        ValueError: If ``since`` is set and a record's ``started_at`` is
            present but cannot be parsed as ISO 8601.
    """
    kept: list[dict[str, object]] = []
    for rec in records:
        if fault is not None and rec.get("fault") != fault:
            continue
        if outcome is not None and rec.get("outcome") != outcome:
            continue
        if vm is not None and rec.get("vm") != vm:
            continue
        if since is not None:
            raw = rec.get("started_at")
            if raw is None:
                continue
            ts = datetime.fromisoformat(str(raw))
            if ts < since:
                continue
        kept.append(rec)
    return kept


def load_record(path: Path) -> dict[str, object]:
    """Read and parse one run-record JSON file.

    Args:
        path: Path to a run-record ``.json`` file.

    Returns:
        The deserialised record as a dict.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_id(runs_dir: Path, id_or_prefix: str) -> Path:
    """Resolve a run id (or unambiguous prefix) to a record file path.

    Matches are made against the filename stem. The stem is the part of the
    filename before ``.json`` (e.g. ``20260422T220314Z-disk-latency-server1``).
    An exact stem match wins over a prefix match.

    Args:
        runs_dir: Directory containing run-record ``.json`` files.
        id_or_prefix: Full stem or any unambiguous prefix of one.

    Returns:
        Absolute path to the matched record file.

    Raises:
        FileNotFoundError: If ``runs_dir`` does not exist or no record matches.
        ValueError: If the prefix matches more than one record.
    """
    if not runs_dir.is_dir():
        raise FileNotFoundError(f"runs directory not found: {runs_dir}")
    candidates = sorted(runs_dir.glob("*.json"))
    for path in candidates:
        if path.stem == id_or_prefix:
            return path
    matches = [p for p in candidates if p.stem.startswith(id_or_prefix)]
    if not matches:
        raise FileNotFoundError(f"no run record matches {id_or_prefix!r}")
    if len(matches) > 1:
        names = ", ".join(p.stem for p in matches)
        raise ValueError(f"ambiguous prefix {id_or_prefix!r}; matches: {names}")
    return matches[0]


def write_run_record(record: dict[str, object], runs_dir: Path) -> Path:
    """Serialise a run record to a timestamped JSON file.

    File name format: ``{compact_ts}-{fault_slug}-{vm}.json``, where
    ``compact_ts`` is microsecond-precision (``%Y%m%dT%H%M%S%fZ``). On the
    rare event that the chosen path already exists (e.g. two parallel-batch
    workers capture the same microsecond), a ``-{n}`` counter suffix is
    appended until a free name is found — this preserves audit-trail
    integrity under v0.19+ fan-out and parallel batches.

    Dots in fault names are replaced with hyphens (e.g. ``vm.freeze`` →
    ``vm-freeze``) to avoid ambiguous file extensions.

    Contents are durably persisted: the temp file is fsync'd before the
    atomic ``os.replace`` so a host crash mid-experiment cannot leave an
    empty record on disk.

    Args:
        record: Run record dict. Must include ``started_at``, ``fault``, ``vm``.
        runs_dir: Directory to write into. Created if it does not exist.

    Returns:
        Absolute path of the written JSON file.
    """
    runs_dir.mkdir(parents=True, exist_ok=True)
    dt = datetime.fromisoformat(str(record["started_at"])).astimezone(UTC)
    compact = dt.strftime("%Y%m%dT%H%M%S%fZ")
    fault_slug = str(record["fault"]).replace(".", "-")
    base = f"{compact}-{fault_slug}-{record['vm']}"
    path = runs_dir / f"{base}.json"
    counter = 1
    while path.exists():
        path = runs_dir / f"{base}-{counter}.json"
        counter += 1
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=runs_dir, suffix=".tmp", delete=False
    ) as fh:
        fh.write(json.dumps(record, indent=2))
        fh.flush()
        os.fsync(fh.fileno())
        tmp_path = Path(fh.name)
    os.replace(tmp_path, path)
    return path
