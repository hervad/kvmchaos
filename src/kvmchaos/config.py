"""TOML config file for safety rails: allowlist and rate limit.

The config file is entirely optional. When absent, kvmchaos behaves as before:
no allowlist enforcement, no rate limiting. This keeps first-run UX intact
while giving team-scale deployments the guardrails they need.

Example ``~/.config/kvmchaos/config.toml``::

    [allowlist]
    vms = ["server1", "server2"]
    patterns = ["staging-*"]

    [rate_limit]
    injects_per_hour = 20
    min_interval_between_destructive_seconds = 300

Lookup order:

1. Explicit path via ``--config PATH``
2. ``$XDG_CONFIG_HOME/kvmchaos/config.toml``
3. ``~/.config/kvmchaos/config.toml``
4. ``/etc/kvmchaos/config.toml``

The first existing file wins; missing files fall through silently.
"""

from __future__ import annotations

import fnmatch
import os
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class AllowlistConfig:
    """VM allowlist by exact name or fnmatch-style pattern."""

    vms: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()

    def is_configured(self) -> bool:
        """Return True if any allowlist rule is set."""
        return bool(self.vms or self.patterns)

    def is_allowed(self, vm_name: str) -> bool:
        """Return True if ``vm_name`` matches the allowlist or no allowlist is set."""
        if not self.is_configured():
            return True
        if vm_name in self.vms:
            return True
        return any(fnmatch.fnmatch(vm_name, p) for p in self.patterns)


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate-limiting guardrails.

    Both values default to ``0`` meaning disabled.
    """

    injects_per_hour: int = 0
    min_interval_between_destructive_seconds: int = 0

    def is_configured(self) -> bool:
        """Return True if any rate-limit rule is set."""
        return self.injects_per_hour > 0 or self.min_interval_between_destructive_seconds > 0


@dataclass(frozen=True)
class Config:
    """Top-level config container."""

    allowlist: AllowlistConfig = field(default_factory=AllowlistConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)


def _candidate_paths() -> list[Path]:
    """Return the ordered list of config file paths to try."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    paths: list[Path] = []
    if xdg:
        paths.append(Path(xdg) / "kvmchaos" / "config.toml")
    paths.append(Path.home() / ".config" / "kvmchaos" / "config.toml")
    paths.append(Path("/etc/kvmchaos/config.toml"))
    return paths


def resolve_config_path(explicit: Path | None = None) -> Path | None:
    """Return the first existing config path, or None if none exist.

    Args:
        explicit: Path passed via ``--config``. Takes precedence.

    Returns:
        Path to an existing config file, or None.

    Raises:
        FileNotFoundError: If ``explicit`` is given but the file does not exist.
    """
    if explicit is not None:
        if not explicit.is_file():
            raise FileNotFoundError(f"config file not found: {explicit}")
        return explicit
    for candidate in _candidate_paths():
        if candidate.is_file():
            return candidate
    return None


def load_config(explicit: Path | None = None) -> Config:
    """Load and parse the config file, or return defaults if absent.

    Args:
        explicit: Optional path override.

    Returns:
        A ``Config`` instance. Empty fields mean "feature disabled".

    Raises:
        FileNotFoundError: If ``explicit`` is given but does not exist.
        tomllib.TOMLDecodeError: If the config file is not valid TOML.
    """
    path = resolve_config_path(explicit)
    if path is None:
        return Config()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    al = data.get("allowlist", {})
    rl = data.get("rate_limit", {})
    return Config(
        allowlist=AllowlistConfig(
            vms=tuple(al.get("vms", [])),
            patterns=tuple(al.get("patterns", [])),
        ),
        rate_limit=RateLimitConfig(
            injects_per_hour=int(rl.get("injects_per_hour", 0)),
            min_interval_between_destructive_seconds=int(
                rl.get("min_interval_between_destructive_seconds", 0)
            ),
        ),
    )


def count_injects_since(records: list[dict[str, object]], since: datetime) -> int:
    """Count run records with ``started_at`` at or after ``since``.

    Args:
        records: Run records as returned by :func:`kvmchaos.report.load_records`.
        since: Lower bound, inclusive. Must be timezone-aware.

    Returns:
        Number of matching records.
    """
    count = 0
    for rec in records:
        raw = rec.get("started_at")
        if raw is None:
            continue
        try:
            ts = datetime.fromisoformat(str(raw))
        except ValueError:
            continue
        if ts >= since:
            count += 1
    return count


def last_destructive_run(records: list[dict[str, object]]) -> datetime | None:
    """Return the ``started_at`` of the most recent destructive run, or None.

    A run is destructive if its fault name is ``vm.kill``. Extend this set as
    new destructive faults are introduced.

    Args:
        records: Run records (any order; this scans all).

    Returns:
        Timezone-aware datetime, or None if no destructive run exists.
    """
    destructive_faults = {"vm.kill"}
    latest: datetime | None = None
    for rec in records:
        if rec.get("fault") not in destructive_faults:
            continue
        raw = rec.get("started_at")
        if raw is None:
            continue
        try:
            ts = datetime.fromisoformat(str(raw))
        except ValueError:
            continue
        if latest is None or ts > latest:
            latest = ts
    return latest


def rate_limit_violation(
    config: RateLimitConfig,
    records: list[dict[str, object]],
    *,
    is_destructive: bool,
    now: datetime | None = None,
) -> str | None:
    """Return a human-readable violation message, or None if the inject is allowed.

    Args:
        config: Active rate-limit configuration.
        records: Existing run records.
        is_destructive: True if the about-to-run fault has ``destructive=True``.
        now: Reference timestamp (for deterministic tests). Defaults to UTC now.

    Returns:
        Error string if the inject should be refused, otherwise None.
    """
    if not config.is_configured():
        return None
    now = now or datetime.now(UTC)
    if config.injects_per_hour > 0:
        hour_ago = now - timedelta(hours=1)
        count = count_injects_since(records, hour_ago)
        if count >= config.injects_per_hour:
            return (
                f"rate limit: {count} injects in the last hour "
                f"(limit: {config.injects_per_hour}/hour)"
            )
    if is_destructive and config.min_interval_between_destructive_seconds > 0:
        last = last_destructive_run(records)
        if last is not None:
            elapsed = (now - last).total_seconds()
            min_interval = config.min_interval_between_destructive_seconds
            if elapsed < min_interval:
                return (
                    f"rate limit: last destructive run was {int(elapsed)}s ago "
                    f"(min interval: {min_interval}s)"
                )
    return None
