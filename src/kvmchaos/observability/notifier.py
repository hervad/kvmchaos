"""Synchronous webhook notifier for kvmchaos observability events.

Posts a single JSON body per event to the configured ``webhook_url`` with a
short timeout. Transport errors (network failure, timeout, non-2xx response)
are logged at WARNING and dropped. The notifier never propagates exceptions:
chaos recovery must not block on an external endpoint outage.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any
from urllib.error import URLError

from kvmchaos.config import NotifierConfig

_LOG = logging.getLogger("kvmchaos.observability.notifier")


class Notifier:
    """Posts event payloads to a configured webhook URL.

    A `NotifierConfig` with an empty ``webhook_url`` makes ``notify`` a no-op.
    Event filtering: when ``cfg.events`` is non-empty, only payloads whose
    ``event`` value is in the set are posted.
    """

    def __init__(self, cfg: NotifierConfig) -> None:
        """Store config and pre-compute the event filter set."""
        self._cfg = cfg
        self._event_filter: frozenset[str] | None = frozenset(cfg.events) if cfg.events else None

    def notify(self, payload: dict[str, Any]) -> None:
        """Post ``payload`` as a JSON body. Never raises.

        Args:
            payload: The event payload. Must contain an ``event`` key.
        """
        if not self._cfg.is_enabled():
            return
        event = payload.get("event")
        if self._event_filter is not None and event not in self._event_filter:
            return
        try:
            body = json.dumps(payload, default=str).encode("utf-8")
        except (TypeError, ValueError) as exc:
            _LOG.warning("notifier: failed to encode payload for event %s: %s", event, exc)
            return
        req = urllib.request.Request(
            self._cfg.webhook_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        if self._cfg.auth_header:
            req.add_header("Authorization", self._cfg.auth_header)
        try:
            with urllib.request.urlopen(req, timeout=self._cfg.timeout_s) as resp:
                status = getattr(resp, "status", 0)
                if not 200 <= status < 300:
                    _LOG.warning("notifier: non-2xx response %s for event %s", status, event)
        except (URLError, TimeoutError, OSError) as exc:
            _LOG.warning("notifier: transport error for event %s: %s", event, exc)
