"""Unit tests for the libvirt C-library error handler bridge."""

from __future__ import annotations

import json

import pytest

from kvmchaos.observability import logging as obs_logging


def _fake_err(
    message: str = "domain is not running",
    code: int = 55,
    domain: int = 10,
    level: int = 2,
) -> tuple:
    """Build an `err` tuple matching libvirt's callback contract (first 4 fields used)."""
    return (code, domain, message, level, "", "", "", 0, 0)


def test_handler_emits_debug_record_with_libvirt_stderr_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from kvmchaos import libvirt_conn

    obs_logging.configure_stderr_logging(verbose=True)
    libvirt_conn._libvirt_error_handler(None, _fake_err(message="oops", code=42))
    captured = capsys.readouterr()
    line = captured.err.strip()
    record = json.loads(line)
    assert record["level"] == "DEBUG"
    assert record["event"] == "libvirt.stderr"
    assert record["message"] == "oops"
    assert record["code"] == 42
    assert record["domain"] == 10
    assert record["libvirt_level"] == 2


def test_handler_suppressed_in_non_verbose_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from kvmchaos import libvirt_conn

    obs_logging.configure_stderr_logging(verbose=False)
    libvirt_conn._libvirt_error_handler(None, _fake_err())
    captured = capsys.readouterr()
    assert captured.err.strip() == ""


def test_register_once_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling _register_once twice registers the handler exactly once."""
    from kvmchaos import libvirt_conn

    libvirt_conn._reset_registration_for_tests()
    calls = []
    monkeypatch.setattr(
        libvirt_conn.libvirt,
        "registerErrorHandler",
        lambda handler, ctx: calls.append((handler, ctx)),
    )
    libvirt_conn._register_once()
    libvirt_conn._register_once()
    libvirt_conn._register_once()
    assert len(calls) == 1
    assert calls[0][0] is libvirt_conn._libvirt_error_handler
    assert calls[0][1] is None


def test_connect_triggers_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect() calls _register_once before libvirt.open."""
    from kvmchaos import libvirt_conn

    libvirt_conn._reset_registration_for_tests()
    calls: list[str] = []

    real_register = libvirt_conn._register_once

    def tracking_register() -> None:
        calls.append("register")
        real_register()

    monkeypatch.setattr(libvirt_conn, "_register_once", tracking_register)

    with libvirt_conn.connect("test:///default"):
        pass

    assert "register" in calls
    assert libvirt_conn._HANDLER_REGISTERED is True
