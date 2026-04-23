"""Tests for the JSON-to-stderr observability logger."""

from __future__ import annotations

import json
import logging

import pytest

from kvmchaos.observability import logging as obs_logging


@pytest.fixture
def _configure_obs_logging() -> None:
    """Reset observability logger state before each test."""
    obs_logging._reset_for_tests()
    yield
    obs_logging._reset_for_tests()


def test_emits_valid_json_with_required_keys(
    _configure_obs_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    obs_logging.configure_stderr_logging(verbose=False)
    logger = logging.getLogger("kvmchaos.observability")
    logger.info("event-payload", extra={"event": "inject.start", "fault": "net.latency"})
    captured = capsys.readouterr()
    line = captured.err.strip()
    record = json.loads(line)
    assert record["event"] == "inject.start"
    assert record["fault"] == "net.latency"
    assert record["level"] == "INFO"
    assert "timestamp" in record


def test_verbose_enables_debug_records(
    _configure_obs_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    obs_logging.configure_stderr_logging(verbose=True)
    logger = logging.getLogger("kvmchaos.observability")
    logger.debug("debug-line", extra={"event": "diagnostic"})
    captured = capsys.readouterr()
    assert captured.err.strip() != ""


def test_non_verbose_suppresses_debug_records(
    _configure_obs_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    obs_logging.configure_stderr_logging(verbose=False)
    logger = logging.getLogger("kvmchaos.observability")
    logger.debug("debug-line", extra={"event": "diagnostic"})
    captured = capsys.readouterr()
    assert captured.err.strip() == ""


def test_non_serialisable_extra_is_coerced(
    _configure_obs_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    obs_logging.configure_stderr_logging(verbose=False)
    logger = logging.getLogger("kvmchaos.observability")

    class Weird:
        def __repr__(self) -> str:
            return "<Weird>"

    logger.info("e", extra={"event": "x", "blob": Weird()})
    captured = capsys.readouterr()
    record = json.loads(captured.err.strip())
    assert record["blob"] == "<Weird>"


def test_configure_is_idempotent(
    _configure_obs_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    obs_logging.configure_stderr_logging(verbose=False)
    obs_logging.configure_stderr_logging(verbose=False)
    logger = logging.getLogger("kvmchaos.observability")
    logger.info("once", extra={"event": "x"})
    captured = capsys.readouterr()
    assert captured.err.count("\n") == 1
