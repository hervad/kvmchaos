"""Event-name constants and the payload shape shared by all observability sinks."""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any

INJECT_START = "inject.start"
INJECT_SUCCESS = "inject.success"
INJECT_ERROR = "inject.error"
REVERT_SUCCESS = "revert.success"
REVERT_ERROR = "revert.error"
EXPERIMENT_START = "experiment.start"
EXPERIMENT_END = "experiment.end"

ALL_EVENTS: tuple[str, ...] = (
    INJECT_START,
    INJECT_SUCCESS,
    INJECT_ERROR,
    REVERT_SUCCESS,
    REVERT_ERROR,
    EXPERIMENT_START,
    EXPERIMENT_END,
)


def _kvmchaos_version() -> str:
    """Return the installed kvmchaos version, or ``'0.0.0+unknown'`` if missing."""
    try:
        return version("kvmchaos")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def build_payload(event: str, **fields: Any) -> dict[str, Any]:
    """Build the canonical event payload used by both sinks.

    Args:
        event: One of the event-name constants exported by this module.
        **fields: Event-specific data (``fault``, ``vm``, ``params``, etc.).

    Returns:
        A new dict containing ``event``, ``timestamp`` (ISO-8601 UTC),
        ``host``, ``kvmchaos_version``, plus all caller-supplied fields.
    """
    payload: dict[str, Any] = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "kvmchaos_version": _kvmchaos_version(),
    }
    payload.update(fields)
    return payload
