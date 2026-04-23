"""Unit tests for the runrecord module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kvmchaos.runrecord import default_runs_dir, write_run_record

_SAMPLE: dict[str, object] = {
    "started_at": "2026-04-22T16:30:00+00:00",
    "ended_at": "2026-04-22T16:30:22+00:00",
    "fault": "vm.freeze",
    "vm": "server1",
    "uri": "qemu:///system",
    "dry_run": False,
    "duration_s": 22,
    "outcome": "success",
    "steps": [
        {"action": "inject", "result": "ok", "duration_ms": 12},
        {"action": "verify", "result": "ok", "duration_ms": 8},
        {"action": "revert", "result": "ok", "duration_ms": 10},
    ],
}


class TestDefaultRunsDir:
    def test_default_without_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        assert default_runs_dir() == Path.home() / ".local" / "state" / "kvmchaos" / "runs"

    def test_respects_xdg_state_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        assert default_runs_dir() == tmp_path / "kvmchaos" / "runs"

    def test_sudo_user_uses_invoking_user_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.setenv("SUDO_USER", "alice")
        fake_pw = MagicMock()
        fake_pw.pw_dir = "/home/alice"
        with patch("kvmchaos.runrecord.pwd.getpwnam", return_value=fake_pw):
            result = default_runs_dir()
        assert result == Path("/home/alice/.local/state/kvmchaos/runs")

    def test_sudo_user_unknown_falls_back_to_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import patch

        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.setenv("SUDO_USER", "ghost")
        with patch("kvmchaos.runrecord.pwd.getpwnam", side_effect=KeyError("ghost")):
            result = default_runs_dir()
        assert result == Path.home() / ".local" / "state" / "kvmchaos" / "runs"

    def test_xdg_takes_precedence_over_sudo_user(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        monkeypatch.setenv("SUDO_USER", "alice")
        assert default_runs_dir() == tmp_path / "kvmchaos" / "runs"


class TestWriteRunRecord:
    def test_creates_directory(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / "runs"
        assert not runs_dir.exists()
        write_run_record(_SAMPLE, runs_dir)
        assert runs_dir.is_dir()

    def test_filename_format(self, tmp_path: Path) -> None:
        path = write_run_record(_SAMPLE, tmp_path)
        assert path.name == "20260422T163000Z-vm-freeze-server1.json"

    def test_dot_to_hyphen_in_fault_name(self, tmp_path: Path) -> None:
        record = {**_SAMPLE, "fault": "net.latency", "vm": "server2"}
        path = write_run_record(record, tmp_path)
        assert "net-latency" in path.name
        assert "." not in path.stem

    def test_content_roundtrips(self, tmp_path: Path) -> None:
        path = write_run_record(_SAMPLE, tmp_path)
        loaded = json.loads(path.read_text())
        assert loaded["fault"] == "vm.freeze"
        assert loaded["vm"] == "server1"
        assert loaded["outcome"] == "success"
        assert len(loaded["steps"]) == 3

    def test_returns_written_path(self, tmp_path: Path) -> None:
        path = write_run_record(_SAMPLE, tmp_path)
        assert path.exists()
        assert path.suffix == ".json"
