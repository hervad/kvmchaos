"""Tests for the report module."""

from __future__ import annotations

import json
from pathlib import Path

from kvmchaos.report import generate, load_records, render_html

_RECORD_SUCCESS: dict[str, object] = {
    "started_at": "2026-04-22T22:03:14+00:00",
    "ended_at": "2026-04-22T22:03:59+00:00",
    "fault": "disk.latency",
    "vm": "server1",
    "uri": "qemu:///system",
    "dry_run": False,
    "duration_s": 45,
    "outcome": "success",
    "steps": [
        {"action": "inject", "result": "ok", "duration_ms": 24},
        {"action": "verify", "result": "ok", "duration_ms": 0},
        {"action": "revert", "result": "ok", "duration_ms": 1},
    ],
}

_RECORD_DRY_RUN: dict[str, object] = {
    "started_at": "2026-04-22T21:47:40+00:00",
    "ended_at": "2026-04-22T21:47:40+00:00",
    "fault": "disk.latency",
    "vm": "server1",
    "uri": "qemu:///system",
    "dry_run": True,
    "duration_s": 0,
    "outcome": "dry_run",
    "steps": [
        {"action": "inject", "result": "skipped", "duration_ms": 0},
        {"action": "verify", "result": "skipped", "duration_ms": 0},
        {"action": "revert", "result": "skipped", "duration_ms": 0},
    ],
}

_RECORD_FAIL: dict[str, object] = {
    "started_at": "2026-04-22T20:00:00+00:00",
    "ended_at": "2026-04-22T20:00:02+00:00",
    "fault": "vm.pause",
    "vm": "<script>alert(1)</script>",
    "uri": "qemu:///system",
    "dry_run": False,
    "duration_s": 2,
    "outcome": "fail",
    "steps": [
        {
            "action": "inject",
            "result": "fail",
            "duration_ms": 500,
            "error": "libvirtError: domain not found",
        },
    ],
}


def _write(dir_: Path, name: str, record: dict[str, object]) -> None:
    (dir_ / f"{name}.json").write_text(json.dumps(record))


class TestLoadRecords:
    def test_returns_empty_list_when_dir_missing(self, tmp_path: Path) -> None:
        assert load_records(tmp_path / "nope") == []

    def test_returns_empty_list_when_dir_empty(self, tmp_path: Path) -> None:
        assert load_records(tmp_path) == []

    def test_loads_all_json_files(self, tmp_path: Path) -> None:
        _write(tmp_path, "a", _RECORD_SUCCESS)
        _write(tmp_path, "b", _RECORD_DRY_RUN)
        records = load_records(tmp_path)
        assert len(records) == 2
        assert {r["outcome"] for r in records} == {"success", "dry_run"}

    def test_ignores_non_json_files(self, tmp_path: Path) -> None:
        _write(tmp_path, "good", _RECORD_SUCCESS)
        (tmp_path / "README.txt").write_text("noise")
        records = load_records(tmp_path)
        assert len(records) == 1

    def test_sorted_newest_first(self, tmp_path: Path) -> None:
        _write(tmp_path, "old", _RECORD_FAIL)  # 20:00:00
        _write(tmp_path, "new", _RECORD_SUCCESS)  # 22:03:14
        records = load_records(tmp_path)
        assert records[0]["started_at"] > records[1]["started_at"]

    def test_skips_unparsable_json(self, tmp_path: Path) -> None:
        _write(tmp_path, "ok", _RECORD_SUCCESS)
        (tmp_path / "bad.json").write_text("{not json")
        records = load_records(tmp_path)
        assert len(records) == 1


class TestRenderHtml:
    def test_empty_records_produces_no_runs_message(self) -> None:
        html = render_html([])
        assert "No runs" in html
        assert "<html" in html
        assert "</html>" in html

    def test_summary_counts_each_outcome(self) -> None:
        html = render_html([_RECORD_SUCCESS, _RECORD_DRY_RUN, _RECORD_FAIL])
        assert "Total: 3" in html
        assert "success: 1" in html
        assert "dry_run: 1" in html
        assert "fail: 1" in html

    def test_summary_shows_date_range(self) -> None:
        html = render_html([_RECORD_SUCCESS, _RECORD_FAIL])
        # Range timestamps are reformatted via _fmt_ts.
        assert "2026-04-22 | 20:00:00 UTC" in html
        assert "2026-04-22 | 22:03:59 UTC" in html
        assert "+00:00" not in html

    def test_summary_range_tolerates_missing_timestamps(self) -> None:
        """Records with absent started_at/ended_at must not corrupt the range display."""
        from kvmchaos.report import render_html

        records = [
            {
                "fault": "vm.pause",
                "vm": "s1",
                "outcome": "success",
                "started_at": "2026-04-22T22:03:14+00:00",
                "ended_at": "2026-04-22T22:03:59+00:00",
                "duration_s": 45,
                "dry_run": False,
                "steps": [],
            },
            {
                "fault": "vm.pause",
                "vm": "s2",
                "outcome": "fail",
                "duration_s": 0,
                "dry_run": False,
                "steps": [],
            },  # missing started_at/ended_at
        ]
        html = render_html(records)
        # Range start must show the real date from record 1, not collapse to ""
        # (empty string is lexicographically less than any real timestamp, so
        # min() without filtering picks "" from the record missing started_at)
        assert "Range: 2026" in html

    def test_table_includes_all_columns(self) -> None:
        html = render_html([_RECORD_SUCCESS])
        for header in ("started_at", "fault", "vm", "outcome", "duration_s", "dry_run"):
            assert f">{header}<" in html

    def test_row_contains_record_values(self) -> None:
        html = render_html([_RECORD_SUCCESS])
        assert "disk.latency" in html
        assert "server1" in html
        assert "success" in html
        assert "45" in html

    def test_row_has_details_with_steps(self) -> None:
        html = render_html([_RECORD_SUCCESS])
        assert "<details>" in html
        assert "inject" in html
        assert "duration_ms" in html

    def test_escapes_html_in_values(self) -> None:
        html = render_html([_RECORD_FAIL])
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestGenerate:
    def test_writes_file_to_output_path(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        runs.mkdir()
        _write(runs, "r", _RECORD_SUCCESS)
        out = tmp_path / "report.html"

        result = generate(out, runs)

        assert result == out
        assert out.is_file()
        content = out.read_text()
        assert "disk.latency" in content

    def test_creates_output_parent_dir(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        runs.mkdir()
        _write(runs, "r", _RECORD_SUCCESS)
        out = tmp_path / "nested" / "dir" / "report.html"

        generate(out, runs)

        assert out.is_file()

    def test_empty_runs_dir_still_writes_file(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        runs.mkdir()
        out = tmp_path / "report.html"

        generate(out, runs)

        assert out.is_file()
        assert "No runs" in out.read_text()


class TestDisplay:
    def test_strips_utc_offset_from_started_at(self) -> None:
        from kvmchaos.report import _display

        assert _display("started_at", "2026-04-22T22:03:14+00:00") == "2026-04-22 | 22:03:14 UTC"

    def test_passes_through_non_timestamp_columns(self) -> None:
        from kvmchaos.report import _display

        assert _display("fault", "disk.latency") == "disk.latency"
        assert _display("duration_s", 45) == "45"

    def test_leaves_non_utc_timestamp_unchanged(self) -> None:
        from kvmchaos.report import _display

        assert _display("started_at", "2026-04-22T22:03:14+02:00") == "2026-04-22T22:03:14+02:00"

    def test_strips_microseconds_from_started_at(self) -> None:
        """Microsecond fractions (added in v0.19.2) are dropped for display."""
        from kvmchaos.report import _display

        assert (
            _display("started_at", "2026-04-22T22:03:14.123456+00:00")
            == "2026-04-22 | 22:03:14 UTC"
        )
