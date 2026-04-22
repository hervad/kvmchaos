"""Tests for _is_remote helper and the net.latency remote guard."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from kvmchaos.cli import _is_remote, app

runner = CliRunner()


class TestIsRemote:
    @pytest.mark.parametrize(
        "uri",
        [
            "qemu:///system",
            "qemu://localhost/system",
            "qemu://127.0.0.1/system",
            "qemu://[::1]/system",
        ],
    )
    def test_local_uris(self, uri: str) -> None:
        assert _is_remote(uri) is False

    @pytest.mark.parametrize(
        "uri",
        [
            "qemu+ssh://192.168.1.10/system",
            "qemu+ssh://hypervisor.local/system",
            "qemu+ssh://root@kvm-host/system",
        ],
    )
    def test_remote_uris(self, uri: str) -> None:
        assert _is_remote(uri) is True


class TestRemoteGuard:
    def test_local_only_fault_with_remote_uri_exits_2(self) -> None:
        result = runner.invoke(
            app,
            [
                "--connect",
                "qemu+ssh://192.168.1.10/system",
                "inject",
                "--yes",
                "net.latency",
                "server1",
            ],
        )
        assert result.exit_code == 2
        assert "requires local execution" in result.stderr

    def test_local_only_fault_with_local_uri_is_not_blocked(self) -> None:
        result = runner.invoke(
            app,
            ["--connect", "test:///default", "inject", "--yes", "--dry-run", "net.latency", "test"],
        )
        assert "requires local execution" not in result.stderr

    def test_non_local_only_fault_with_remote_uri_not_blocked(self) -> None:
        # vm.pause is not local_only — guard must not trigger.
        # Connection will fail (can't reach 192.168.1.10 in tests) but
        # the error must not be the guard message.
        result = runner.invoke(
            app,
            [
                "--connect",
                "qemu+ssh://192.168.1.10/system",
                "inject",
                "--yes",
                "vm.pause",
                "server1",
            ],
        )
        assert "requires local execution" not in result.stderr
