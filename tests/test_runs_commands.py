"""Tests for the `runs list` and `runs show` CLI subcommands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kvmchaos.cli import app
from kvmchaos.runrecord import load_record, resolve_id

runner = CliRunner()


def _write(runs: Path, name: str, record: dict[str, object]) -> Path:
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{name}.json"
    path.write_text(json.dumps(record))
    return path


def _sample(started_at: str, fault: str = "vm.pause", vm: str = "server1") -> dict[str, object]:
    return {
        "started_at": started_at,
        "ended_at": started_at,
        "fault": fault,
        "vm": vm,
        "uri": "qemu:///system",
        "dry_run": False,
        "duration_s": 1,
        "outcome": "success",
        "steps": [],
    }


class TestResolveId:
    def test_exact_match(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "20260422T220314Z-disk-latency-server1", _sample("2026-04-22T22:03:14+00:00")
        )
        path = resolve_id(tmp_path, "20260422T220314Z-disk-latency-server1")
        assert path.name == "20260422T220314Z-disk-latency-server1.json"

    def test_unambiguous_prefix(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "20260422T220314Z-disk-latency-server1", _sample("2026-04-22T22:03:14+00:00")
        )
        _write(tmp_path, "20260422T100000Z-vm-pause-server2", _sample("2026-04-22T10:00:00+00:00"))
        path = resolve_id(tmp_path, "20260422T22")
        assert "disk-latency" in path.name

    def test_ambiguous_prefix_raises(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "20260422T220314Z-disk-latency-server1", _sample("2026-04-22T22:03:14+00:00")
        )
        _write(tmp_path, "20260422T220500Z-vm-pause-server1", _sample("2026-04-22T22:05:00+00:00"))
        with pytest.raises(ValueError, match="ambiguous"):
            resolve_id(tmp_path, "20260422T22")

    def test_no_match_raises(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "20260422T220314Z-disk-latency-server1", _sample("2026-04-22T22:03:14+00:00")
        )
        with pytest.raises(FileNotFoundError):
            resolve_id(tmp_path, "nonexistent")

    def test_missing_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            resolve_id(tmp_path / "nope", "anything")

    def test_record_id_round_trip(self, tmp_path: Path) -> None:
        """The id shown in `runs list` must resolve back to the written file."""
        from kvmchaos.cli import _record_id
        from kvmchaos.runrecord import write_run_record

        record = _sample("2026-04-22T22:03:14.123456+00:00")
        path = write_run_record(record, tmp_path)
        derived_id = _record_id(tmp_path, record)
        assert path.stem == derived_id


class TestLoadRecord:
    def test_loads_and_parses_json(self, tmp_path: Path) -> None:
        record = _sample("2026-04-22T22:03:14+00:00")
        path = _write(tmp_path, "x", record)
        loaded = load_record(path)
        assert loaded["fault"] == "vm.pause"
        assert loaded["vm"] == "server1"


class TestRunsListCommand:
    def test_empty_dir_prints_no_runs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(app, ["runs", "list"])
        assert result.exit_code == 0
        assert "No runs." in result.stdout

    def test_populated_dir_shows_table(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        runs = tmp_path / "kvmchaos" / "runs"
        _write(runs, "20260422T220000Z-vm-pause-server1", _sample("2026-04-22T22:00:00+00:00"))
        _write(
            runs,
            "20260422T100000Z-disk-latency-server2",
            _sample("2026-04-22T10:00:00+00:00", "disk.latency", "server2"),
        )
        result = runner.invoke(app, ["runs", "list"])
        assert result.exit_code == 0
        assert "vm.pause" in result.stdout
        assert "disk.latency" in result.stdout
        # Newest first: T22 row precedes T10 row.
        assert result.stdout.index("T22") < result.stdout.index("T10")

    def test_limit_option(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        runs = tmp_path / "kvmchaos" / "runs"
        for hour in range(5):
            _write(
                runs,
                f"20260422T{hour:02d}0000Z-vm-pause-server1",
                _sample(f"2026-04-22T{hour:02d}:00:00+00:00"),
            )
        result = runner.invoke(app, ["runs", "list", "--limit", "2"])
        assert result.exit_code == 0
        # 2 rows + 1 header line = 3 non-empty lines.
        body_lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        assert len(body_lines) == 3

    def test_runs_dir_option(self, tmp_path: Path) -> None:
        custom = tmp_path / "custom"
        _write(custom, "20260422T220000Z-vm-pause-server1", _sample("2026-04-22T22:00:00+00:00"))
        result = runner.invoke(app, ["runs", "list", "--runs-dir", str(custom)])
        assert result.exit_code == 0
        assert "vm.pause" in result.stdout


class TestRunsShowCommand:
    def test_exact_id(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "20260422T220314Z-disk-latency-server1",
            _sample("2026-04-22T22:03:14+00:00", "disk.latency"),
        )
        result = runner.invoke(
            app,
            [
                "runs",
                "show",
                "20260422T220314Z-disk-latency-server1",
                "--runs-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["fault"] == "disk.latency"

    def test_unambiguous_prefix(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "20260422T220314Z-disk-latency-server1",
            _sample("2026-04-22T22:03:14+00:00", "disk.latency"),
        )
        result = runner.invoke(app, ["runs", "show", "20260422T22", "--runs-dir", str(tmp_path)])
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["fault"] == "disk.latency"

    def test_ambiguous_prefix_exits_2(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "20260422T220314Z-disk-latency-server1", _sample("2026-04-22T22:03:14+00:00")
        )
        _write(tmp_path, "20260422T220500Z-vm-pause-server1", _sample("2026-04-22T22:05:00+00:00"))
        result = runner.invoke(app, ["runs", "show", "20260422T22", "--runs-dir", str(tmp_path)])
        assert result.exit_code == 2
        assert "ambiguous" in result.stdout.lower() or "ambiguous" in (result.stderr or "").lower()

    def test_unknown_id_exits_2(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "20260422T220314Z-disk-latency-server1", _sample("2026-04-22T22:03:14+00:00")
        )
        result = runner.invoke(app, ["runs", "show", "nope", "--runs-dir", str(tmp_path)])
        assert result.exit_code == 2

    def test_corrupted_json_exits_2_with_message(self, tmp_path: Path) -> None:
        """A corrupted run record must produce a helpful error message, not a traceback."""
        bad = tmp_path / "20260422T220314Z-vm-pause-server1.json"
        bad.write_text("{ not valid json }")
        result = runner.invoke(
            app, ["runs", "show", "20260422T220314Z-vm-pause-server1", "--runs-dir", str(tmp_path)]
        )
        assert result.exit_code == 2
        combined = result.output + (result.stderr or "")
        assert any(w in combined.lower() for w in ("corrupt", "invalid", "json", "decode"))


class TestRunsListFilters:
    def test_fault_filter(self, tmp_path: Path) -> None:
        _write(tmp_path, "20260422T100000Z-vm-pause-server1", _sample("2026-04-22T10:00:00+00:00"))
        _write(
            tmp_path,
            "20260422T110000Z-disk-latency-server1",
            _sample("2026-04-22T11:00:00+00:00", "disk.latency"),
        )
        result = runner.invoke(
            app,
            ["runs", "list", "--runs-dir", str(tmp_path), "--fault", "disk.latency"],
        )
        assert result.exit_code == 0
        assert "disk.latency" in result.stdout
        assert "vm.pause" not in result.stdout

    def test_outcome_filter(self, tmp_path: Path) -> None:
        ok = _sample("2026-04-22T10:00:00+00:00")
        bad = _sample("2026-04-22T11:00:00+00:00")
        bad["outcome"] = "fail"
        _write(tmp_path, "20260422T100000Z-vm-pause-server1", ok)
        _write(tmp_path, "20260422T110000Z-vm-pause-server1", bad)
        result = runner.invoke(
            app, ["runs", "list", "--runs-dir", str(tmp_path), "--outcome", "fail"]
        )
        assert result.exit_code == 0
        body_lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        # Header + exactly one data row.
        assert len(body_lines) == 2

    def test_vm_filter(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "20260422T100000Z-vm-pause-server1",
            _sample("2026-04-22T10:00:00+00:00", vm="server1"),
        )
        _write(
            tmp_path,
            "20260422T110000Z-vm-pause-server2",
            _sample("2026-04-22T11:00:00+00:00", vm="server2"),
        )
        result = runner.invoke(
            app, ["runs", "list", "--runs-dir", str(tmp_path), "--vm", "server2"]
        )
        assert result.exit_code == 0
        assert "server2" in result.stdout
        # server1 row absent.
        body_lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        assert len(body_lines) == 2

    def test_since_filter_date_only(self, tmp_path: Path) -> None:
        _write(tmp_path, "20260421T120000Z-vm-pause-s", _sample("2026-04-21T12:00:00+00:00"))
        _write(tmp_path, "20260423T120000Z-vm-pause-s", _sample("2026-04-23T12:00:00+00:00"))
        result = runner.invoke(
            app, ["runs", "list", "--runs-dir", str(tmp_path), "--since", "2026-04-22"]
        )
        assert result.exit_code == 0
        assert "2026-04-23" in result.stdout
        assert "2026-04-21" not in result.stdout

    def test_filters_yielding_no_rows(self, tmp_path: Path) -> None:
        _write(tmp_path, "20260422T100000Z-vm-pause-s", _sample("2026-04-22T10:00:00+00:00"))
        result = runner.invoke(
            app, ["runs", "list", "--runs-dir", str(tmp_path), "--fault", "vm.kill"]
        )
        assert result.exit_code == 0
        assert "No runs." in result.stdout

    def test_bad_since_exits_nonzero(self, tmp_path: Path) -> None:
        _write(tmp_path, "20260422T100000Z-vm-pause-s", _sample("2026-04-22T10:00:00+00:00"))
        result = runner.invoke(
            app,
            ["runs", "list", "--runs-dir", str(tmp_path), "--since", "not-a-date"],
        )
        assert result.exit_code != 0


class TestReportFilters:
    def test_fault_filter(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        _write(runs, "20260422T100000Z-vm-pause-s", _sample("2026-04-22T10:00:00+00:00"))
        _write(
            runs,
            "20260422T110000Z-disk-latency-s",
            _sample("2026-04-22T11:00:00+00:00", "disk.latency"),
        )
        out = tmp_path / "r.html"
        result = runner.invoke(
            app,
            [
                "report",
                "--output",
                str(out),
                "--runs-dir",
                str(runs),
                "--fault",
                "disk.latency",
            ],
        )
        assert result.exit_code == 0
        body = out.read_text()
        assert "disk.latency" in body
        assert "vm.pause" not in body

    def test_outcome_filter(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        ok = _sample("2026-04-22T10:00:00+00:00")
        bad = _sample("2026-04-22T11:00:00+00:00")
        bad["outcome"] = "fail"
        _write(runs, "20260422T100000Z-vm-pause-s", ok)
        _write(runs, "20260422T110000Z-vm-pause-s", bad)
        out = tmp_path / "r.html"
        result = runner.invoke(
            app,
            ["report", "--output", str(out), "--runs-dir", str(runs), "--outcome", "fail"],
        )
        assert result.exit_code == 0
        body = out.read_text()
        assert "fail: 1" in body
        assert "success" not in body or "success: " not in body
