"""Per-run JSON record writer for kvmchaos.

Writes one JSON file per inject invocation to a XDG-compliant directory.
Each file contains the full lifecycle of a single inject run: fault, VM,
URI, timestamps, per-step outcomes, and overall result.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def default_runs_dir() -> Path:
    """Return the XDG-compliant default directory for per-run JSON records.

    Returns:
        Path under ``$XDG_STATE_HOME/kvmchaos/runs/``, defaulting to
        ``~/.local/state/kvmchaos/runs/`` when ``XDG_STATE_HOME`` is unset.
    """
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "kvmchaos" / "runs"


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
    dt = datetime.fromisoformat(str(record["started_at"]))
    compact = dt.strftime("%Y%m%dT%H%M%SZ")
    fault_slug = str(record["fault"]).replace(".", "-")
    filename = f"{compact}-{fault_slug}-{record['vm']}.json"
    path = runs_dir / filename
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path
