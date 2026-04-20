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
