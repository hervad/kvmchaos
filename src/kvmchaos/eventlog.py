"""Append-only JSONL event log for kvmchaos runs.

Events are written via the stdlib `logging` framework so callers never
touch a file handle directly. One line per event, JSON-encoded, UTF-8.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "kvmchaos.events"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB before rotation
_BACKUP_COUNT = 3


class _JsonFormatter(logging.Formatter):
    """Formats log records as single JSON lines.

    Expects `record.msg` to be a dict of event fields.
    A `ts` field (ISO 8601 UTC) is always prepended.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        if isinstance(record.msg, dict):
            payload.update(record.msg)
        else:
            payload["message"] = record.getMessage()
        return json.dumps(payload, separators=(",", ":"), sort_keys=False)


def default_log_path() -> Path:
    """Return the XDG-compliant default path for the event log.

    Returns:
        Path under `$XDG_STATE_HOME/kvmchaos/events.log`, defaulting to
        `~/.local/state/kvmchaos/events.log` when `XDG_STATE_HOME` is unset.
    """
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "kvmchaos" / "events.log"


def configure_logging(path: Path | None = None) -> None:
    """Attach a rotating JSONL handler to the `kvmchaos.events` logger.

    Idempotent: once a handler is attached, repeated calls are no-ops regardless
    of `path`. The first call's path wins for the lifetime of the process.

    Args:
        path: Target log file. Defaults to `default_log_path()`.
    """
    target = path or default_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    # propagate=False is load-bearing: record.msg is a raw dict, not a string.
    # Re-enabling propagation would send the raw dict to the root logger's handlers.
    logger.propagate = False

    if logger.handlers:
        return

    handler = RotatingFileHandler(
        target, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)


def log_event(**fields: object) -> None:
    """Write a single JSON event line to the event log.

    Keyword arguments become top-level keys in the JSON object. A `ts`
    field (ISO 8601 UTC) is added automatically by the formatter.

    Common keys: `action`, `fault`, `vm`, `result`, `duration_ms`, `error`.

    Args:
        **fields: Arbitrary key-value pairs to include in the event record.
    """
    logging.getLogger(_LOGGER_NAME).info(fields)
