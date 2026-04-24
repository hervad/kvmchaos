"""Tests for the JSON-to-stderr observability logger."""

from __future__ import annotations

import json
import logging
from pathlib import Path

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


def test_caller_supplied_timestamp_overrides_formatter(
    _configure_obs_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `timestamp` in ``extra`` overrides the formatter's auto-generated one."""
    obs_logging.configure_stderr_logging(verbose=False)
    logger = logging.getLogger("kvmchaos.observability")
    logger.info("e", extra={"event": "x", "timestamp": "2099-01-01T00:00:00+00:00"})
    captured = capsys.readouterr()
    record = json.loads(captured.err.strip())
    assert record["timestamp"] == "2099-01-01T00:00:00+00:00"


def test_json_log_path_writes_pure_jsonl(_configure_obs_logging: None, tmp_path: Path) -> None:
    """--json-log target receives one JSON object per logger call."""
    log_file = tmp_path / "events.jsonl"
    obs_logging.configure_stderr_logging(verbose=False, json_log_path=log_file)
    logger = logging.getLogger("kvmchaos.observability")
    logger.info("first", extra={"event": "inject.start", "fault": "vm.pause"})
    logger.info("second", extra={"event": "inject.success", "fault": "vm.pause"})

    content = log_file.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if line]
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["event"] == "inject.start"
    assert second["event"] == "inject.success"


def test_json_log_path_is_idempotent(_configure_obs_logging: None, tmp_path: Path) -> None:
    """Re-configuring with the same path does not double-attach the file handler."""
    log_file = tmp_path / "events.jsonl"
    obs_logging.configure_stderr_logging(verbose=False, json_log_path=log_file)
    obs_logging.configure_stderr_logging(verbose=False, json_log_path=log_file)
    logger = logging.getLogger("kvmchaos.observability")
    logger.info("once", extra={"event": "x"})
    content = log_file.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if line]
    assert len(lines) == 1


def test_reset_closes_file_handler(_configure_obs_logging: None, tmp_path: Path) -> None:
    """_reset_for_tests detaches and closes the file handler."""
    log_file = tmp_path / "events.jsonl"
    obs_logging.configure_stderr_logging(verbose=False, json_log_path=log_file)
    logger = logging.getLogger("kvmchaos.observability")
    file_handlers_before = [h for h in logger.handlers if getattr(h, "_kvmchaos_obs_file", False)]
    assert len(file_handlers_before) == 1
    assert not file_handlers_before[0].stream.closed

    obs_logging._reset_for_tests()

    file_handlers_after = [
        h
        for h in logging.getLogger("kvmchaos.observability").handlers
        if getattr(h, "_kvmchaos_obs_file", False)
    ]
    assert file_handlers_after == []
    # FileHandler.close() sets stream to None; None stream means closed.
    assert file_handlers_before[0].stream is None
