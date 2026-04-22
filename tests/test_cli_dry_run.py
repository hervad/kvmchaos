"""CLI tests for the --dry-run flag on the inject command."""

from typer.testing import CliRunner

from kvmchaos.cli import app

runner = CliRunner()

_CONNECT = ["--connect", "test:///default"]


class TestDryRunHappyPath:
    def test_dry_run_exits_zero(self):
        result = runner.invoke(app, [*_CONNECT, "inject", "--dry-run", "--yes", "vm.pause", "test"])
        assert result.exit_code == 0

    def test_dry_run_prints_all_three_steps(self):
        result = runner.invoke(app, [*_CONNECT, "inject", "--dry-run", "--yes", "vm.pause", "test"])
        assert "[dry-run] would: inject" in result.stdout
        assert "[dry-run] would: verify" in result.stdout
        assert "[dry-run] would: revert" in result.stdout

    def test_dry_run_short_flag(self):
        result = runner.invoke(app, [*_CONNECT, "inject", "-n", "--yes", "vm.pause", "test"])
        assert result.exit_code == 0
        assert "[dry-run]" in result.stdout

    def test_dry_run_with_vm_kill(self):
        result = runner.invoke(app, [*_CONNECT, "inject", "--dry-run", "--yes", "vm.kill", "test"])
        assert result.exit_code == 0
        assert "[dry-run] would: inject vm.kill on test" in result.stdout


class TestDryRunValidation:
    def test_dry_run_unknown_fault_exits_2(self):
        result = runner.invoke(app, [*_CONNECT, "inject", "--dry-run", "--yes", "bogus", "test"])
        assert result.exit_code == 2

    def test_dry_run_unknown_vm_exits_2(self):
        result = runner.invoke(
            app, [*_CONNECT, "inject", "--dry-run", "--yes", "vm.pause", "no-such-vm"]
        )
        assert result.exit_code == 2

    def test_dry_run_skips_confirmation_prompt(self):
        # --dry-run must never prompt; no input supplied and it should still exit 0.
        result = runner.invoke(
            app,
            [*_CONNECT, "inject", "--dry-run", "vm.pause", "test"],
        )
        assert result.exit_code == 0
        assert "Continue?" not in result.output
