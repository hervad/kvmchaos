"""Integration tests: CLI commands emit observability events."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from kvmchaos.cli import app
from kvmchaos.observability import events as ev
from kvmchaos.observability.notifier import Notifier

# The package __init__ re-exports `emit` as a bare function, so a plain
# `import kvmchaos.observability.emit as emit_mod` resolves to the function.
# importlib.import_module gives us the actual submodule object so that
# monkeypatch can set _NOTIFIER on the correct namespace.
emit_mod = importlib.import_module("kvmchaos.observability.emit")


@pytest.fixture
def captured_notifier(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Install a mock Notifier and return it for assertion."""
    fake = MagicMock(spec=Notifier)
    monkeypatch.setattr(emit_mod, "_NOTIFIER", fake)
    return fake


def _events_for(notifier_mock: MagicMock) -> list[str]:
    """Extract the event name from each notify() call."""
    return [call.args[0]["event"] for call in notifier_mock.notify.call_args_list]


def test_inject_emits_start_success_revert_success(
    captured_notifier: MagicMock,
) -> None:
    """inject vm.pause emits inject.start, inject.success, revert.success in order."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--connect",
            "test:///default",
            "inject",
            "vm.pause",
            "test",
            "--duration",
            "0",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    seq = _events_for(captured_notifier)
    assert ev.INJECT_START in seq
    assert ev.INJECT_SUCCESS in seq
    assert ev.REVERT_SUCCESS in seq
    start_call = next(
        c for c in captured_notifier.notify.call_args_list if c.args[0]["event"] == ev.INJECT_START
    )
    assert start_call.args[0]["fault"] == "vm.pause"
    assert start_call.args[0]["vm"] == "test"
    assert start_call.args[0]["duration_s"] == 0
