"""Tests for runrecord.filter_records."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kvmchaos.runrecord import filter_records


def _rec(
    started_at: str,
    *,
    fault: str = "vm.pause",
    vm: str = "server1",
    outcome: str = "success",
) -> dict[str, object]:
    return {
        "started_at": started_at,
        "fault": fault,
        "vm": vm,
        "outcome": outcome,
    }


_A = _rec("2026-04-22T10:00:00+00:00", fault="disk.latency", vm="server1", outcome="success")
_B = _rec("2026-04-22T12:00:00+00:00", fault="vm.pause", vm="server2", outcome="dry_run")
_C = _rec("2026-04-22T18:00:00+00:00", fault="disk.latency", vm="server2", outcome="fail")
_D = _rec("2026-04-23T08:00:00+00:00", fault="vm.pause", vm="server1", outcome="success")


class TestFilterRecordsNoOp:
    def test_no_filters_returns_input(self) -> None:
        assert filter_records([_A, _B, _C]) == [_A, _B, _C]

    def test_all_none_returns_input(self) -> None:
        assert filter_records([_A, _B, _C], since=None, fault=None, outcome=None, vm=None) == [
            _A,
            _B,
            _C,
        ]


class TestFilterRecordsSince:
    def test_since_drops_older(self) -> None:
        since = datetime(2026, 4, 22, 13, 0, tzinfo=UTC)
        result = filter_records([_A, _B, _C, _D], since=since)
        assert result == [_C, _D]

    def test_since_is_inclusive(self) -> None:
        since = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)
        result = filter_records([_A, _B, _C, _D], since=since)
        assert _B in result


class TestFilterRecordsFault:
    def test_fault_exact_match(self) -> None:
        result = filter_records([_A, _B, _C, _D], fault="disk.latency")
        assert result == [_A, _C]

    def test_fault_no_match_returns_empty(self) -> None:
        assert filter_records([_A, _B], fault="vm.kill") == []


class TestFilterRecordsOutcome:
    def test_outcome_filter(self) -> None:
        result = filter_records([_A, _B, _C, _D], outcome="fail")
        assert result == [_C]

    def test_dry_run_outcome(self) -> None:
        result = filter_records([_A, _B], outcome="dry_run")
        assert result == [_B]


class TestFilterRecordsVm:
    def test_vm_filter(self) -> None:
        result = filter_records([_A, _B, _C, _D], vm="server2")
        assert result == [_B, _C]


class TestFilterRecordsCombined:
    def test_all_filters_together(self) -> None:
        since = datetime(2026, 4, 22, 11, 0, tzinfo=UTC)
        result = filter_records(
            [_A, _B, _C, _D],
            since=since,
            fault="disk.latency",
            outcome="fail",
            vm="server2",
        )
        assert result == [_C]

    def test_empty_intersection(self) -> None:
        # disk.latency exists; server2 hosts it; but outcome=dry_run does not.
        assert filter_records([_A, _B, _C], fault="disk.latency", outcome="dry_run") == []


class TestFilterRecordsBadInputs:
    def test_missing_started_at_skipped_when_since_set(self) -> None:
        bad = {"fault": "vm.pause", "vm": "s", "outcome": "success"}
        since = datetime(2026, 4, 22, 0, 0, tzinfo=UTC)
        result = filter_records([_A, bad], since=since)
        assert bad not in result
        assert _A in result

    def test_unparseable_started_at_skipped_when_since_set(self) -> None:
        bad = {"started_at": "not a date", "fault": "x", "vm": "y", "outcome": "success"}
        since = datetime(2026, 4, 22, 0, 0, tzinfo=UTC)
        with pytest.raises(ValueError):
            filter_records([bad], since=since)
