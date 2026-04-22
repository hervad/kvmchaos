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
        assert "requires local execution" in result.output

    def test_local_only_fault_with_local_uri_is_not_blocked(self) -> None:
        result = runner.invoke(
            app,
            ["--connect", "test:///default", "inject", "--yes", "--dry-run", "net.latency", "test"],
        )
        assert "requires local execution" not in result.output
