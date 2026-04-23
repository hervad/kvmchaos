"""Tests for the webhook Notifier."""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import patch
from urllib.error import URLError

import pytest

from kvmchaos.config import NotifierConfig
from kvmchaos.observability.notifier import Notifier


class _FakeResp:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def read(self) -> bytes:
        return b""


def _enabled_cfg(**overrides: Any) -> NotifierConfig:
    base = {
        "webhook_url": "https://example.test/hook",
        "auth_header": "",
        "timeout_s": 3,
        "events": (),
    }
    base.update(overrides)
    return NotifierConfig(**base)


def test_disabled_notifier_is_noop() -> None:
    n = Notifier(NotifierConfig())
    with patch("urllib.request.urlopen") as m:
        n.notify({"event": "inject.start"})
        m.assert_not_called()


def test_happy_path_posts_payload() -> None:
    n = Notifier(_enabled_cfg())
    with patch("urllib.request.urlopen", return_value=_FakeResp(200)) as m:
        n.notify({"event": "inject.start", "fault": "net.latency"})
    req = m.call_args.args[0]
    assert req.full_url == "https://example.test/hook"
    body = json.loads(req.data.decode("utf-8"))
    assert body == {"event": "inject.start", "fault": "net.latency"}
    assert req.get_header("Content-type") == "application/json"


def test_auth_header_is_passed() -> None:
    n = Notifier(_enabled_cfg(auth_header="Bearer abc"))
    with patch("urllib.request.urlopen", return_value=_FakeResp(200)) as m:
        n.notify({"event": "inject.start"})
    req = m.call_args.args[0]
    assert req.get_header("Authorization") == "Bearer abc"


def test_event_filter_skips_unsubscribed_events() -> None:
    n = Notifier(_enabled_cfg(events=("inject.error",)))
    with patch("urllib.request.urlopen", return_value=_FakeResp(200)) as m:
        n.notify({"event": "inject.start"})
        m.assert_not_called()
        n.notify({"event": "inject.error", "error": "boom"})
        m.assert_called_once()


def test_timeout_kwarg_used() -> None:
    n = Notifier(_enabled_cfg(timeout_s=7))
    with patch("urllib.request.urlopen", return_value=_FakeResp(200)) as m:
        n.notify({"event": "inject.start"})
    assert m.call_args.kwargs["timeout"] == 7


def test_network_error_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    # Ensure the loggers propagate (may be disabled by other tests' setup)
    obs_logger = logging.getLogger("kvmchaos.observability")
    obs_logger.propagate = True
    notifier_logger = logging.getLogger("kvmchaos.observability.notifier")
    notifier_logger.propagate = True
    # Ensure the logger itself can emit at WARNING level
    notifier_logger.setLevel(logging.WARNING)

    n = Notifier(_enabled_cfg())
    with (
        caplog.at_level(logging.WARNING),
        patch("urllib.request.urlopen", side_effect=URLError("nope")),
    ):
        n.notify({"event": "inject.start"})  # must not raise
    # caplog captures records from any logger that propagates to root
    # so check both the message and the logger name
    assert any(
        "notifier" in r.message.lower() and r.name == "kvmchaos.observability.notifier"
        for r in caplog.records
    ), f"No notifier records found. Got: {[(r.name, r.message) for r in caplog.records]}"


def test_non_2xx_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    # Ensure the loggers propagate (may be disabled by other tests' setup)
    obs_logger = logging.getLogger("kvmchaos.observability")
    obs_logger.propagate = True
    notifier_logger = logging.getLogger("kvmchaos.observability.notifier")
    notifier_logger.propagate = True
    # Ensure the logger itself can emit at WARNING level
    notifier_logger.setLevel(logging.WARNING)

    n = Notifier(_enabled_cfg())
    with (
        caplog.at_level(logging.WARNING),
        patch("urllib.request.urlopen", return_value=_FakeResp(500)),
    ):
        n.notify({"event": "inject.start"})  # must not raise
    # caplog captures records from any logger that propagates to root
    # so check both the message and the logger name
    assert any(
        "notifier" in r.message.lower() and r.name == "kvmchaos.observability.notifier"
        for r in caplog.records
    ), f"No notifier records found. Got: {[(r.name, r.message) for r in caplog.records]}"


def test_non_serialisable_payload_coerced() -> None:
    n = Notifier(_enabled_cfg())

    class Weird:
        def __repr__(self) -> str:
            return "<Weird>"

    with patch("urllib.request.urlopen", return_value=_FakeResp(200)) as m:
        n.notify({"event": "x", "blob": Weird()})
    body = json.loads(m.call_args.args[0].data.decode("utf-8"))
    assert body["blob"] == "<Weird>"
