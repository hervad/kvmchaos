"""Observability sinks for kvmchaos: structured logs and webhook notifier."""

from __future__ import annotations

from kvmchaos.observability import events
from kvmchaos.observability.emit import emit, set_notifier
from kvmchaos.observability.logging import configure_stderr_logging
from kvmchaos.observability.notifier import Notifier

__all__ = [
    "Notifier",
    "configure_stderr_logging",
    "emit",
    "events",
    "set_notifier",
]
