"""CLI tests using Typer's test runner."""

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
