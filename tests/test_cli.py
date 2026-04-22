"""CLI tests using Typer's test runner."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kvmchaos import __version__
from kvmchaos.cli import app

runner = CliRunner()


class TestVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout


class TestListVms:
    def test_lists_test_domain(self):
        result = runner.invoke(app, ["--connect", "test:///default", "list-vms"])
        assert result.exit_code == 0
        assert "test" in result.stdout


class TestListFaults:
    def test_lists_both_faults(self):
        result = runner.invoke(app, ["list-faults"])
        assert result.exit_code == 0
        assert "vm.pause" in result.stdout
        assert "vm.kill" in result.stdout


class TestStateName:
    def test_known_states(self):
        from kvmchaos.cli import _state_name

        assert _state_name(0) == "nostate"
        assert _state_name(1) == "running"
        assert _state_name(3) == "paused"
        assert _state_name(5) == "shutoff"

    def test_unknown_state_fallback(self):
        from kvmchaos.cli import _state_name

        assert _state_name(99) == "state99"


class TestInject:
    def test_inject_vm_pause_happy_path(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(
            app,
            ["--connect", "test:///default", "inject", "vm.pause", "test", "--yes"],
        )
        assert result.exit_code == 0, result.stdout

        log = (tmp_path / "kvmchaos" / "events.log").read_text().splitlines()
        actions = [json.loads(line)["action"] for line in log if line.strip()]
        assert actions == ["inject", "verify", "revert"]

    def test_inject_unknown_fault_returns_2(self):
        result = runner.invoke(
            app,
            ["--connect", "test:///default", "inject", "bogus", "test", "--yes"],
        )
        assert result.exit_code == 2

    def test_inject_missing_vm_returns_2(self):
        result = runner.invoke(
            app,
            ["--connect", "test:///default", "inject", "vm.pause", "nope", "--yes"],
        )
        assert result.exit_code == 2

    def test_inject_without_yes_aborts_on_no(self):
        result = runner.invoke(
            app,
            ["--connect", "test:///default", "inject", "vm.pause", "test"],
            input="n\n",
        )
        assert result.exit_code == 1


class TestRunRecord:
    def test_record_written_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(
            app,
            [
                "--connect",
                "test:///default",
                "inject",
                "--yes",
                "--duration",
                "0",
                "vm.pause",
                "test",
            ],
        )
        assert result.exit_code == 0
        runs_dir = tmp_path / "kvmchaos" / "runs"
        records = list(runs_dir.glob("*.json"))
        assert len(records) == 1
        data = json.loads(records[0].read_text())
        assert data["fault"] == "vm.pause"
        assert data["vm"] == "test"
        assert data["outcome"] == "success"
        assert data["dry_run"] is False
        assert [s["action"] for s in data["steps"]] == ["inject", "verify", "revert"]

    def test_record_written_for_dry_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(
            app,
            [
                "--connect",
                "test:///default",
                "inject",
                "--yes",
                "--dry-run",
                "vm.pause",
                "test",
            ],
        )
        assert result.exit_code == 0
        runs_dir = tmp_path / "kvmchaos" / "runs"
        records = list(runs_dir.glob("*.json"))
        assert len(records) == 1
        data = json.loads(records[0].read_text())
        assert data["dry_run"] is True
        assert all(s["result"] == "skipped" for s in data["steps"])
        assert data["outcome"] == "success"

    def test_record_path_printed_to_stdout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(
            app,
            [
                "--connect",
                "test:///default",
                "inject",
                "--yes",
                "--duration",
                "0",
                "vm.pause",
                "test",
            ],
        )
        assert result.exit_code == 0
        assert "Run record:" in result.stdout
