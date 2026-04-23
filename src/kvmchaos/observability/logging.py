"""JSON-formatted stderr logging for kvmchaos observability events.

Writes one JSON object per record to stderr. Designed for journald capture
when run under a systemd unit and for ``| jq`` piping during ad-hoc CLI use.
The handler attaches to a dedicated ``kvmchaos.observability`` logger so it
does not interfere with the file-based ``kvmchaos.events`` logger in
``eventlog.py``.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

LOGGER_NAME = "kvmchaos.observability"

_RESERVED_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Render a log record as a single JSON line.

    Includes ``timestamp`` (ISO-8601 UTC), ``level``, ``message`` (the rendered
    log message), and any extra fields attached via ``logger.info(..., extra=...)``.
    Non-JSON-serialisable values are coerced via ``str()`` so logging never crashes.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render a log record as a single JSON line.

        If the caller supplies a ``timestamp`` field via ``extra={...}``, the
        caller's value wins — this lets `emit()` share one timestamp across the
        JSON log line and the webhook payload.
        """
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_stderr_logging(*, verbose: bool) -> None:
    """Attach the JSON stderr handler to the observability logger.

    Idempotent: repeat calls update the level but do not duplicate handlers.

    Args:
        verbose: If True, set level to ``DEBUG``; otherwise ``INFO``.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    if any(getattr(h, "_kvmchaos_obs", False) for h in logger.handlers):
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler._kvmchaos_obs = True  # type: ignore[attr-defined]
    logger.addHandler(handler)


def _reset_for_tests() -> None:
    """Remove all handlers from the observability logger. Test-only helper."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
