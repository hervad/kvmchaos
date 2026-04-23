"""CLI tests using Typer's test runner."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class TestDoctor:
    def test_runs_and_prints_checks(self, tmp_path, monkeypatch):
        # Use the test:/// URI so libvirt is always reachable, and point the
        # runs dir at a tmp path so the write probe succeeds.
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(app, ["--connect", "test:///default", "doctor"])
        assert "kvmchaos doctor" in result.stdout
        assert "tc binary on PATH" in result.stdout
        assert "libvirtd reachable" in result.stdout
        assert "runs dir writable" in result.stdout
        # exit may be 0 or 1 depending on host (e.g. missing libvirt group in CI)
        assert result.exit_code in (0, 1, 2)

    def test_reports_libvirt_unreachable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(app, ["--connect", "qemu+tcp://127.0.0.1:1/system", "doctor"])
        # exit 2 because libvirtd will fail to connect
        assert result.exit_code == 2
        assert "libvirtd reachable" in result.stdout
        assert "FAIL" in result.stdout


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
        assert data["outcome"] == "dry_run"

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

    def test_record_written_on_inject_fail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mock_fault = MagicMock()
        mock_fault.description = "test fault"
        mock_fault.destructive = False
        mock_fault.local_only = False
        mock_fault.inject.side_effect = RuntimeError("injected failure")

        with patch("kvmchaos.cli.FAULTS", {"vm.pause": mock_fault}):
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
        assert result.exit_code == 1
        runs_dir = tmp_path / "kvmchaos" / "runs"
        records = list(runs_dir.glob("*.json"))
        assert len(records) == 1
        data = json.loads(records[0].read_text())
        assert data["outcome"] == "fail"
        assert data["steps"][0]["result"] == "fail"

    def test_record_written_on_verify_fail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mock_fault = MagicMock()
        mock_fault.description = "test fault"
        mock_fault.destructive = False
        mock_fault.local_only = False
        mock_fault.verify.side_effect = RuntimeError("verify failed")

        with patch("kvmchaos.cli.FAULTS", {"vm.pause": mock_fault}):
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
        assert result.exit_code == 1
        runs_dir = tmp_path / "kvmchaos" / "runs"
        records = list(runs_dir.glob("*.json"))
        assert len(records) == 1
        data = json.loads(records[0].read_text())
        assert data["outcome"] == "fail"
        assert data["steps"][1]["result"] == "fail"
        assert len(data["steps"]) == 3  # inject ok, verify fail, revert attempted


class TestBandwidthFlag:
    def test_disk_latency_appears_in_list_faults(self) -> None:
        result = runner.invoke(app, ["list-faults"])
        assert result.exit_code == 0
        assert "disk.latency" in result.stdout

    def test_bandwidth_flag_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock, patch

        from kvmchaos.faults.disk_latency import DiskLatencyFault

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

        def capturing_run_step(func, domain, *, action, fault_name, vm, dry_run=False):
            return {"action": action, "result": "skipped", "duration_ms": 0}

        with (
            patch("kvmchaos.cli._run_step", side_effect=capturing_run_step),
            patch("kvmchaos.cli.FAULTS", {"disk.latency": DiskLatencyFault()}),
            patch("kvmchaos.cli.connect") as mock_conn,
        ):
            mock_domain = MagicMock()
            mock_conn.return_value.__enter__.return_value.lookupByName.return_value = mock_domain
            result = runner.invoke(
                app,
                [
                    "--connect",
                    "test:///default",
                    "inject",
                    "--yes",
                    "--dry-run",
                    "--bandwidth",
                    "2",
                    "disk.latency",
                    "test",
                ],
            )
        assert result.exit_code == 0


class TestReport:
    def test_empty_runs_dir_exits_zero(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        runs.mkdir()
        out = tmp_path / "r.html"
        result = runner.invoke(app, ["report", "--output", str(out), "--runs-dir", str(runs)])
        assert result.exit_code == 0
        assert out.is_file()
        assert "No runs" in out.read_text()
        assert f"Report: {out}" in result.stdout

    def test_uses_default_runs_dir_via_xdg(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        runs = tmp_path / "kvmchaos" / "runs"
        runs.mkdir(parents=True)
        (runs / "a.json").write_text(
            json.dumps(
                {
                    "started_at": "2026-04-22T22:00:00+00:00",
                    "ended_at": "2026-04-22T22:00:01+00:00",
                    "fault": "vm.pause",
                    "vm": "server1",
                    "uri": "qemu:///system",
                    "dry_run": False,
                    "duration_s": 1,
                    "outcome": "success",
                    "steps": [],
                }
            )
        )
        out = tmp_path / "r.html"
        result = runner.invoke(app, ["report", "--output", str(out)])
        assert result.exit_code == 0
        body = out.read_text()
        assert "vm.pause" in body
        assert "server1" in body


class TestDiskFillCli:
    def test_disk_fill_appears_in_list_faults(self) -> None:
        result = runner.invoke(app, ["list-faults"])
        assert result.exit_code == 0
        assert "disk.fill" in result.stdout

    def test_size_flag_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock, patch

        from kvmchaos.faults.disk_fill import DiskFillFault

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

        def capturing_run_step(func, domain, *, action, fault_name, vm, dry_run=False):
            return {"action": action, "result": "skipped", "duration_ms": 0}

        with (
            patch("kvmchaos.cli._run_step", side_effect=capturing_run_step),
            patch("kvmchaos.cli.FAULTS", {"disk.fill": DiskFillFault()}),
            patch("kvmchaos.cli.connect") as mock_conn,
        ):
            mock_domain = MagicMock()
            mock_conn.return_value.__enter__.return_value.lookupByName.return_value = mock_domain
            result = runner.invoke(
                app,
                [
                    "--connect",
                    "test:///default",
                    "inject",
                    "--yes",
                    "--dry-run",
                    "--size",
                    "512",
                    "disk.fill",
                    "test",
                ],
            )
        assert result.exit_code == 0


class TestInterruptedInject:
    def test_revert_runs_on_keyboard_interrupt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mock_fault = MagicMock()
        mock_fault.description = "test fault"
        mock_fault.destructive = False
        mock_fault.local_only = False

        with (
            patch("kvmchaos.cli.FAULTS", {"vm.pause": mock_fault}),
            patch("kvmchaos.cli.time.sleep", side_effect=KeyboardInterrupt),
        ):
            result = runner.invoke(
                app,
                [
                    "--connect",
                    "test:///default",
                    "inject",
                    "--yes",
                    "--duration",
                    "30",
                    "vm.pause",
                    "test",
                ],
            )

        mock_fault.revert.assert_called_once()
        assert result.exit_code == 1

    def test_interrupted_record_has_interrupted_outcome(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import patch

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

        with patch("kvmchaos.cli.time.sleep", side_effect=KeyboardInterrupt):
            runner.invoke(
                app,
                [
                    "--connect",
                    "test:///default",
                    "inject",
                    "--yes",
                    "--duration",
                    "30",
                    "vm.pause",
                    "test",
                ],
            )

        runs_dir = tmp_path / "kvmchaos" / "runs"
        records = list(runs_dir.glob("*.json"))
        assert len(records) == 1
        data = json.loads(records[0].read_text())
        assert data["outcome"] == "interrupted"
        assert any(s["action"] == "revert" for s in data["steps"])


class TestClockSkewCli:
    def test_clock_skew_appears_in_list_faults(self) -> None:
        result = runner.invoke(app, ["list-faults"])
        assert result.exit_code == 0
        assert "clock.skew" in result.stdout

    def test_skew_flag_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock, patch

        from kvmchaos.faults.clock_skew import ClockSkewFault

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

        def capturing_run_step(func, domain, *, action, fault_name, vm, dry_run=False):
            return {"action": action, "result": "skipped", "duration_ms": 0}

        with (
            patch("kvmchaos.cli._run_step", side_effect=capturing_run_step),
            patch("kvmchaos.cli.FAULTS", {"clock.skew": ClockSkewFault()}),
            patch("kvmchaos.cli.connect") as mock_conn,
        ):
            mock_domain = MagicMock()
            mock_conn.return_value.__enter__.return_value.lookupByName.return_value = mock_domain
            result = runner.invoke(
                app,
                [
                    "--connect",
                    "test:///default",
                    "inject",
                    "--yes",
                    "--dry-run",
                    "--skew",
                    "7200",
                    "clock.skew",
                    "test",
                ],
            )
        assert result.exit_code == 0

    def test_skew_zero_rejected(self) -> None:
        result = runner.invoke(
            app,
            ["inject", "--yes", "--skew", "0", "clock.skew", "test"],
        )
        assert result.exit_code == 2
        assert "no-op" in result.output


class TestNetPacketLossCli:
    def test_net_packet_loss_appears_in_list_faults(self) -> None:
        result = runner.invoke(app, ["list-faults"])
        assert result.exit_code == 0
        assert "net.packet-loss" in result.stdout

    def test_loss_flag_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock, patch

        from kvmchaos.faults.net_packet_loss import NetPacketLossFault

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

        def capturing_run_step(func, domain, *, action, fault_name, vm, dry_run=False):
            return {"action": action, "result": "skipped", "duration_ms": 0}

        with (
            patch("kvmchaos.cli._run_step", side_effect=capturing_run_step),
            patch("kvmchaos.cli.FAULTS", {"net.packet-loss": NetPacketLossFault()}),
            patch("kvmchaos.cli.connect") as mock_conn,
        ):
            mock_domain = MagicMock()
            mock_conn.return_value.__enter__.return_value.lookupByName.return_value = mock_domain
            result = runner.invoke(
                app,
                [
                    "--connect",
                    "test:///default",
                    "inject",
                    "--yes",
                    "--dry-run",
                    "--loss",
                    "25",
                    "net.packet-loss",
                    "test",
                ],
            )
        assert result.exit_code == 0


class TestNetBandwidthCli:
    def test_net_bandwidth_appears_in_list_faults(self) -> None:
        result = runner.invoke(app, ["list-faults"])
        assert result.exit_code == 0
        assert "net.bandwidth" in result.stdout

    def test_rate_flag_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock, patch

        from kvmchaos.faults.net_bandwidth import NetBandwidthFault

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

        def capturing_run_step(func, domain, *, action, fault_name, vm, dry_run=False):
            return {"action": action, "result": "skipped", "duration_ms": 0}

        with (
            patch("kvmchaos.cli._run_step", side_effect=capturing_run_step),
            patch("kvmchaos.cli.FAULTS", {"net.bandwidth": NetBandwidthFault()}),
            patch("kvmchaos.cli.connect") as mock_conn,
        ):
            mock_domain = MagicMock()
            mock_conn.return_value.__enter__.return_value.lookupByName.return_value = mock_domain
            result = runner.invoke(
                app,
                [
                    "--connect",
                    "test:///default",
                    "inject",
                    "--yes",
                    "--dry-run",
                    "--rate",
                    "512",
                    "net.bandwidth",
                    "test",
                ],
            )
        assert result.exit_code == 0


class TestNetCorruptCli:
    def test_net_corrupt_appears_in_list_faults(self) -> None:
        result = runner.invoke(app, ["list-faults"])
        assert result.exit_code == 0
        assert "net.corrupt" in result.stdout

    def test_corrupt_flag_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock, patch

        from kvmchaos.faults.net_corrupt import NetCorruptFault

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

        def capturing_run_step(func, domain, *, action, fault_name, vm, dry_run=False):
            return {"action": action, "result": "skipped", "duration_ms": 0}

        with (
            patch("kvmchaos.cli._run_step", side_effect=capturing_run_step),
            patch("kvmchaos.cli.FAULTS", {"net.corrupt": NetCorruptFault()}),
            patch("kvmchaos.cli.connect") as mock_conn,
        ):
            mock_domain = MagicMock()
            mock_conn.return_value.__enter__.return_value.lookupByName.return_value = mock_domain
            result = runner.invoke(
                app,
                [
                    "inject",
                    "--yes",
                    "--dry-run",
                    "--corrupt",
                    "5",
                    "net.corrupt",
                    "test",
                ],
            )
        assert result.exit_code == 0


class TestNetPartitionCli:
    def test_net_partition_appears_in_list_faults(self) -> None:
        result = runner.invoke(app, ["list-faults"])
        assert result.exit_code == 0
        assert "net.partition" in result.stdout


class TestAllowlist:
    def test_inject_blocked_when_vm_not_in_allowlist(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        cfg = tmp_path / "config.toml"
        cfg.write_text('[allowlist]\nvms = ["other"]\n')

        result = runner.invoke(
            app,
            [
                "inject",
                "--yes",
                "--dry-run",
                "--config",
                str(cfg),
                "vm.pause",
                "server1",
            ],
        )
        assert result.exit_code == 2
        assert "not in the allowlist" in result.output

    def test_inject_allowed_with_matching_pattern(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        cfg = tmp_path / "config.toml"
        cfg.write_text('[allowlist]\npatterns = ["server-*"]\n')
        result = runner.invoke(
            app,
            [
                "--connect",
                "test:///default",
                "inject",
                "--yes",
                "--dry-run",
                "--config",
                str(cfg),
                "vm.pause",
                "test",
            ],
        )
        # 'test' doesn't match 'server-*' — should be blocked
        assert result.exit_code == 2
        assert "not in the allowlist" in result.output

    def test_force_bypasses_allowlist(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        cfg = tmp_path / "config.toml"
        cfg.write_text('[allowlist]\nvms = ["other"]\n')
        result = runner.invoke(
            app,
            [
                "--connect",
                "test:///default",
                "inject",
                "--yes",
                "--dry-run",
                "--force",
                "--config",
                str(cfg),
                "vm.pause",
                "test",
            ],
        )
        assert result.exit_code == 0

    def test_invalid_config_path_exits_2(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(
            app,
            [
                "inject",
                "--yes",
                "--dry-run",
                "--config",
                str(tmp_path / "does-not-exist.toml"),
                "vm.pause",
                "test",
            ],
        )
        assert result.exit_code == 2
        assert "config file not found" in result.output


class TestRateLimit:
    def test_hourly_limit_blocks_inject(self, tmp_path, monkeypatch) -> None:
        from datetime import UTC, datetime

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        runs = tmp_path / "kvmchaos" / "runs"
        runs.mkdir(parents=True)
        now = datetime.now(UTC).isoformat()
        for i in range(3):
            (runs / f"rec{i}.json").write_text(
                f'{{"started_at": "{now}", "fault": "vm.pause", "vm": "x"}}'
            )

        cfg = tmp_path / "config.toml"
        cfg.write_text("[rate_limit]\ninjects_per_hour = 3\n")

        result = runner.invoke(
            app,
            [
                "--connect",
                "test:///default",
                "inject",
                "--yes",
                "--dry-run",
                "--config",
                str(cfg),
                "vm.pause",
                "test",
            ],
        )
        assert result.exit_code == 2
        assert "rate limit" in result.output


class TestAbortAll:
    def test_reports_nothing_when_no_active_faults(self) -> None:
        with patch("kvmchaos.cli.connect") as mock_conn:
            mock_conn.return_value.__enter__.return_value.listAllDomains.return_value = []
            result = runner.invoke(app, ["abort-all"])
        assert result.exit_code == 0
        assert "No active net.* faults" in result.output

    def test_reverts_active_netem_qdisc(self) -> None:
        import libvirt as _libvirt

        domain = MagicMock()
        domain.name.return_value = "server1"
        domain.state.return_value = (_libvirt.VIR_DOMAIN_RUNNING, 1)

        with (
            patch("kvmchaos.cli.connect") as mock_conn,
            patch("kvmchaos.tc.tap_device", return_value="vnet0"),
            patch("kvmchaos.tc.show_qdisc", return_value="qdisc netem 8001: root loss 10%"),
            patch("kvmchaos.tc.del_root_qdisc") as mock_del,
        ):
            mock_conn.return_value.__enter__.return_value.listAllDomains.return_value = [domain]
            result = runner.invoke(app, ["abort-all", "--yes"])
        assert result.exit_code == 0
        assert "reverted: server1" in result.output
        mock_del.assert_called_once_with("vnet0")

    def test_skips_non_running_domains(self) -> None:
        import libvirt as _libvirt

        domain = MagicMock()
        domain.name.return_value = "shutoff-vm"
        domain.state.return_value = (_libvirt.VIR_DOMAIN_SHUTOFF, 1)

        with patch("kvmchaos.cli.connect") as mock_conn:
            mock_conn.return_value.__enter__.return_value.listAllDomains.return_value = [domain]
            result = runner.invoke(app, ["abort-all"])
        assert result.exit_code == 0
        assert "No active" in result.output

    def test_user_aborts_without_yes(self) -> None:
        import libvirt as _libvirt

        domain = MagicMock()
        domain.name.return_value = "server1"
        domain.state.return_value = (_libvirt.VIR_DOMAIN_RUNNING, 1)

        with (
            patch("kvmchaos.cli.connect") as mock_conn,
            patch("kvmchaos.tc.tap_device", return_value="vnet0"),
            patch("kvmchaos.tc.show_qdisc", return_value="qdisc netem 8001: root"),
            patch("kvmchaos.cli.confirm", return_value=False),
        ):
            mock_conn.return_value.__enter__.return_value.listAllDomains.return_value = [domain]
            result = runner.invoke(app, ["abort-all"])
        assert result.exit_code == 1
        assert "Aborted" in result.output
