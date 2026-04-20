"""Tests for JSONL event log."""

import json
import logging
from pathlib import Path

import pytest

from kvmchaos.eventlog import configure_logging, log_event


@pytest.fixture(autouse=True)
def reset_event_logger():
    """Clear kvmchaos.events logger handlers before each test."""
    logger = logging.getLogger("kvmchaos.events")
    logger.handlers.clear()
    yield
    logger.handlers.clear()


def test_log_event_writes_json_line(tmp_path: Path):
    log_file = tmp_path / "events.log"
    configure_logging(log_file)

    log_event(action="inject", fault="vm.pause", vm="web1", result="ok", duration_ms=42)

    # Flush handlers so the write hits disk before we read
    logging.getLogger("kvmchaos.events").handlers[0].flush()

    line = log_file.read_text().strip()
    record = json.loads(line)
    assert record["action"] == "inject"
    assert record["fault"] == "vm.pause"
    assert record["vm"] == "web1"
    assert record["result"] == "ok"
    assert record["duration_ms"] == 42
    assert "ts" in record


def test_log_event_includes_error_field(tmp_path: Path):
    log_file = tmp_path / "events.log"
    configure_logging(log_file)

    log_event(
        action="error", fault="vm.kill", vm="web1", result="fail", duration_ms=7, error="boom"
    )

    logging.getLogger("kvmchaos.events").handlers[0].flush()
    record = json.loads(log_file.read_text().strip())
    assert record["error"] == "boom"


def test_configure_logging_creates_parent_dir(tmp_path: Path):
    log_file = tmp_path / "nested" / "events.log"
    configure_logging(log_file)
    assert log_file.parent.is_dir()


def test_configure_logging_is_idempotent(tmp_path: Path):
    log_file = tmp_path / "events.log"
    configure_logging(log_file)
    configure_logging(log_file)
    logger = logging.getLogger("kvmchaos.events")
    assert len(logger.handlers) == 1
