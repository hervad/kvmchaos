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
from pathlib import Path
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


def configure_stderr_logging(*, verbose: bool, json_log_path: Path | None = None) -> None:
    """Attach JSON handlers to the observability logger.

    Always attaches a stderr stream handler. Optionally also attaches a
    file handler that writes pure JSONL to ``json_log_path``.

    Idempotent: repeat calls update the level but do not duplicate handlers.

    Args:
        verbose: If True, set level to ``DEBUG``; otherwise ``INFO``.
        json_log_path: If set, append structured events to this file as
            pure JSONL. File is opened in append mode, created if missing.

    Raises:
        OSError: If ``json_log_path`` is set but cannot be opened.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    if not any(getattr(h, "_kvmchaos_obs", False) for h in logger.handlers):
        stream_handler = logging.StreamHandler(stream=sys.stderr)
        stream_handler.setFormatter(JsonFormatter())
        stream_handler._kvmchaos_obs = True  # type: ignore[attr-defined]
        logger.addHandler(stream_handler)
    if json_log_path is not None and not any(
        getattr(h, "_kvmchaos_obs_file", False) for h in logger.handlers
    ):
        file_handler = logging.FileHandler(str(json_log_path), mode="a", encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        file_handler._kvmchaos_obs_file = True  # type: ignore[attr-defined]
        logger.addHandler(file_handler)


def _reset_for_tests() -> None:
    """Remove all handlers and restore propagate flag on observability loggers.

    Test-only helper. Restores propagation so `caplog` (which depends on the
    root logger seeing child records) keeps working in subsequent tests.
    """
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.propagate = True
    notifier_logger = logging.getLogger(LOGGER_NAME + ".notifier")
    notifier_logger.propagate = True
