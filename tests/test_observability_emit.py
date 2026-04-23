"""Tests for the observability event payload builder."""

from __future__ import annotations

import re

from kvmchaos.observability import events


def test_event_names_are_dotted_lowercase() -> None:
    """All exported event names follow the `<scope>.<verb>` convention."""
    assert events.INJECT_START == "inject.start"
    assert events.INJECT_SUCCESS == "inject.success"
    assert events.INJECT_ERROR == "inject.error"
    assert events.REVERT_SUCCESS == "revert.success"
    assert events.REVERT_ERROR == "revert.error"
    assert events.EXPERIMENT_START == "experiment.start"
    assert events.EXPERIMENT_END == "experiment.end"


def test_build_payload_includes_required_fields() -> None:
    """`build_payload` injects timestamp, host, version, and event name."""
    payload = events.build_payload(events.INJECT_START, fault="net.latency", vm="vm1")
    assert payload["event"] == "inject.start"
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)", payload["timestamp"]
    )
    assert isinstance(payload["host"], str) and payload["host"]
    assert isinstance(payload["kvmchaos_version"], str) and payload["kvmchaos_version"]
    assert payload["fault"] == "net.latency"
    assert payload["vm"] == "vm1"


def test_build_payload_preserves_extra_fields() -> None:
    """Arbitrary kwargs end up as top-level keys."""
    payload = events.build_payload(
        events.INJECT_START, fault="x", vm="y", params={"ms": 200}, duration_s=30
    )
    assert payload["params"] == {"ms": 200}
    assert payload["duration_s"] == 30


def test_kvmchaos_version_fallback_when_metadata_missing(monkeypatch) -> None:
    """`_kvmchaos_version` returns the sentinel when the package is not installed."""
    from importlib.metadata import PackageNotFoundError

    def _raise(_name: str) -> str:
        raise PackageNotFoundError("kvmchaos")

    monkeypatch.setattr("kvmchaos.observability.events.version", _raise)
    assert events._kvmchaos_version() == "0.0.0+unknown"
