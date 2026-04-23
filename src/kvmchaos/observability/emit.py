"""Fan-out for observability events: stderr JSON log + webhook notifier.

The CLI startup wires a single `Notifier` instance into this module via
`set_notifier()`. Call sites then use `emit(event, **fields)` once per event.
"""

from __future__ import annotations

import logging
from typing import Any

from kvmchaos.observability.events import build_payload
from kvmchaos.observability.notifier import Notifier

_LOG = logging.getLogger("kvmchaos.observability")
_NOTIFIER: Notifier | None = None


def set_notifier(notifier: Notifier | None) -> None:
    """Install the process-wide notifier (or unset by passing ``None``)."""
    global _NOTIFIER
    _NOTIFIER = notifier


def emit(event: str, **fields: Any) -> None:
    """Fan an event out to the JSON stderr log and the webhook notifier.

    Args:
        event: One of the constants in `kvmchaos.observability.events`.
        **fields: Event-specific data merged into the payload.
    """
    payload = build_payload(event, **fields)
    _LOG.info(event, extra={k: v for k, v in payload.items() if k != "message"})
    if _NOTIFIER is not None:
        _NOTIFIER.notify(payload)
