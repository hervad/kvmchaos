"""Per-run JSON record writer for kvmchaos.

Writes one JSON file per inject invocation to a XDG-compliant directory.
Each file contains the full lifecycle of a single inject run: fault, VM,
URI, timestamps, per-step outcomes, and overall result.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def default_runs_dir() -> Path:
    """Return the XDG-compliant default directory for per-run JSON records.

    Returns:
        Path under ``$XDG_STATE_HOME/kvmchaos/runs/``, defaulting to
        ``~/.local/state/kvmchaos/runs/`` when ``XDG_STATE_HOME`` is unset.
    """
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "kvmchaos" / "runs"


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

    File name format: ``{compact_ts}-{fault_slug}-{vm}.json``.
    Dots in fault names are replaced with hyphens (e.g. ``vm.freeze`` →
    ``vm-freeze``) to avoid ambiguous file extensions.

    Args:
        record: Run record dict. Must include ``started_at``, ``fault``, ``vm``.
        runs_dir: Directory to write into. Created if it does not exist.

    Returns:
        Absolute path of the written JSON file.
    """
    runs_dir.mkdir(parents=True, exist_ok=True)
    dt = datetime.fromisoformat(str(record["started_at"])).astimezone(UTC)
    compact = dt.strftime("%Y%m%dT%H%M%SZ")
    fault_slug = str(record["fault"]).replace(".", "-")
    filename = f"{compact}-{fault_slug}-{record['vm']}.json"
    path = runs_dir / filename
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path
