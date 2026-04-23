"""Tests for kvmchaos.config — TOML loading, allowlist, rate limits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kvmchaos.config import (
    AllowlistConfig,
    Config,
    ConfigError,
    RateLimitConfig,
    count_injects_since,
    last_destructive_run,
    load_config,
    rate_limit_violation,
    resolve_config_path,
)


class TestAllowlistConfig:
    def test_empty_allows_all(self):
        al = AllowlistConfig()
        assert al.is_allowed("anything")
        assert al.is_configured() is False

    def test_exact_match(self):
        al = AllowlistConfig(vms=("server1", "server2"))
        assert al.is_allowed("server1")
        assert not al.is_allowed("server3")

    def test_glob_pattern(self):
        al = AllowlistConfig(patterns=("test-*",))
        assert al.is_allowed("test-foo")
        assert al.is_allowed("test-bar")
        assert not al.is_allowed("prod-foo")

    def test_exact_or_pattern(self):
        al = AllowlistConfig(vms=("prod-a",), patterns=("test-*",))
        assert al.is_allowed("prod-a")
        assert al.is_allowed("test-x")
        assert not al.is_allowed("prod-b")


class TestRateLimitConfig:
    def test_zero_disabled(self):
        rl = RateLimitConfig()
        assert rl.is_configured() is False

    def test_any_value_enables(self):
        assert RateLimitConfig(injects_per_hour=10).is_configured()
        assert RateLimitConfig(min_interval_between_destructive_seconds=60).is_configured()


class TestLoadConfig:
    def test_absent_file_returns_default(self, tmp_path: Path):
        result = load_config(None)
        assert isinstance(result, Config)

    def test_explicit_missing_raises(self, tmp_path: Path):
        missing = tmp_path / "nope.toml"
        with pytest.raises(FileNotFoundError):
            load_config(missing)

    def test_parses_full_config(self, tmp_path: Path):
        path = tmp_path / "config.toml"
        path.write_text(
            "[allowlist]\n"
            'vms = ["a", "b"]\n'
            'patterns = ["test-*"]\n'
            "[rate_limit]\n"
            "injects_per_hour = 20\n"
            "min_interval_between_destructive_seconds = 300\n",
        )
        cfg = load_config(path)
        assert cfg.allowlist.vms == ("a", "b")
        assert cfg.allowlist.patterns == ("test-*",)
        assert cfg.rate_limit.injects_per_hour == 20
        assert cfg.rate_limit.min_interval_between_destructive_seconds == 300

    def test_partial_config_uses_defaults(self, tmp_path: Path):
        path = tmp_path / "config.toml"
        path.write_text('[allowlist]\nvms = ["only-one"]\n')
        cfg = load_config(path)
        assert cfg.allowlist.vms == ("only-one",)
        assert cfg.rate_limit.injects_per_hour == 0


class TestResolveConfigPath:
    def test_explicit_takes_precedence(self, tmp_path: Path):
        path = tmp_path / "c.toml"
        path.write_text("")
        assert resolve_config_path(path) == path

    def test_explicit_missing_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            resolve_config_path(tmp_path / "missing.toml")

    def test_returns_none_when_no_file_exists(self, monkeypatch, tmp_path: Path):
        # Point XDG_CONFIG_HOME and HOME at empty dirs so nothing is found.
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        # /etc/kvmchaos/config.toml might exist on the dev machine; accept either.
        result = resolve_config_path(None)
        assert result is None or result == Path("/etc/kvmchaos/config.toml")


class TestRateLimitViolation:
    def _rec(self, started_at: datetime, fault: str = "vm.pause") -> dict[str, object]:
        return {"started_at": started_at.isoformat(), "fault": fault}

    def test_disabled_returns_none(self):
        assert rate_limit_violation(RateLimitConfig(), [], is_destructive=False) is None

    def test_under_hourly_limit_allowed(self):
        now = datetime.now(UTC)
        recs = [self._rec(now - timedelta(minutes=10))]
        cfg = RateLimitConfig(injects_per_hour=5)
        assert rate_limit_violation(cfg, recs, is_destructive=False, now=now) is None

    def test_at_hourly_limit_blocked(self):
        now = datetime.now(UTC)
        recs = [self._rec(now - timedelta(minutes=i)) for i in range(5)]
        cfg = RateLimitConfig(injects_per_hour=5)
        msg = rate_limit_violation(cfg, recs, is_destructive=False, now=now)
        assert msg is not None
        assert "5 injects" in msg

    def test_old_records_dont_count(self):
        now = datetime.now(UTC)
        recs = [self._rec(now - timedelta(hours=2))]
        cfg = RateLimitConfig(injects_per_hour=1)
        assert rate_limit_violation(cfg, recs, is_destructive=False, now=now) is None

    def test_destructive_interval_blocked(self):
        now = datetime.now(UTC)
        recs = [self._rec(now - timedelta(seconds=30), fault="vm.kill")]
        cfg = RateLimitConfig(min_interval_between_destructive_seconds=300)
        msg = rate_limit_violation(cfg, recs, is_destructive=True, now=now)
        assert msg is not None
        assert "destructive" in msg

    def test_destructive_interval_elapsed(self):
        now = datetime.now(UTC)
        recs = [self._rec(now - timedelta(seconds=600), fault="vm.kill")]
        cfg = RateLimitConfig(min_interval_between_destructive_seconds=300)
        assert rate_limit_violation(cfg, recs, is_destructive=True, now=now) is None

    def test_destructive_interval_ignored_for_safe_fault(self):
        now = datetime.now(UTC)
        recs = [self._rec(now - timedelta(seconds=30), fault="vm.kill")]
        cfg = RateLimitConfig(min_interval_between_destructive_seconds=300)
        assert rate_limit_violation(cfg, recs, is_destructive=False, now=now) is None


class TestCountInjectsSince:
    def test_counts_only_recent(self):
        now = datetime.now(UTC)
        recs = [
            {"started_at": (now - timedelta(minutes=10)).isoformat()},
            {"started_at": (now - timedelta(hours=2)).isoformat()},
            {"started_at": (now - timedelta(minutes=30)).isoformat()},
        ]
        assert count_injects_since(recs, now - timedelta(hours=1)) == 2

    def test_skips_missing_or_unparseable(self):
        recs: list[dict[str, object]] = [
            {},
            {"started_at": None},
            {"started_at": "not-a-date"},
            {"started_at": datetime.now(UTC).isoformat()},
        ]
        assert count_injects_since(recs, datetime.now(UTC) - timedelta(hours=1)) == 1


class TestLastDestructiveRun:
    def test_returns_latest(self):
        now = datetime.now(UTC)
        recs = [
            {"fault": "vm.kill", "started_at": (now - timedelta(hours=2)).isoformat()},
            {"fault": "vm.kill", "started_at": (now - timedelta(minutes=10)).isoformat()},
            {"fault": "vm.pause", "started_at": now.isoformat()},
        ]
        result = last_destructive_run(recs)
        assert result is not None
        assert (now - result).total_seconds() < 700  # ~10 minutes ago

    def test_returns_none_when_no_destructive(self):
        recs = [{"fault": "vm.pause", "started_at": datetime.now(UTC).isoformat()}]
        assert last_destructive_run(recs) is None


class TestNotifierConfig:
    def test_notifier_section_parsed(self, tmp_path: Path) -> None:
        """A populated [notifier] section becomes a NotifierConfig."""
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text(
            "[notifier]\n"
            'webhook_url = "https://example.com/h"\n'
            'auth_header = "Bearer t"\n'
            "timeout_s = 5\n"
            'events = ["inject.start", "inject.error"]\n',
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        assert cfg.notifier.webhook_url == "https://example.com/h"
        assert cfg.notifier.auth_header == "Bearer t"
        assert cfg.notifier.timeout_s == 5
        assert cfg.notifier.events == ("inject.start", "inject.error")

    def test_notifier_section_absent_yields_disabled(self, tmp_path: Path) -> None:
        """Missing [notifier] yields a disabled (no webhook) NotifierConfig."""
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("[allowlist]\nvms = []\n", encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg.notifier.webhook_url == ""
        assert cfg.notifier.is_enabled() is False

    def test_notifier_malformed_webhook_url_raises(self, tmp_path: Path) -> None:
        """Non-string webhook_url is a ConfigError."""
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text("[notifier]\nwebhook_url = 42\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(cfg_path)

    def test_notifier_malformed_events_raises(self, tmp_path: Path) -> None:
        """events must be a list of strings; a string scalar is a ConfigError."""
        cfg_path = tmp_path / "config.toml"
        cfg_path.write_text(
            '[notifier]\nwebhook_url = "x"\nevents = "inject.start"\n',
            encoding="utf-8",
        )
        with pytest.raises(ConfigError):
            load_config(cfg_path)
