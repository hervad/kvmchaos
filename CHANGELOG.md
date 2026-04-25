# Changelog

All notable changes to kvmchaos. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are
[semver](https://semver.org/).

## [Unreleased]

## [0.19.0] — 2026-04-25

### Added
- `vms` list field on experiment steps for fan-out: inject the same fault
  on multiple VMs simultaneously (`vms = ["db1", "db2"]`).
- `parallel` flag on experiment steps: consecutive `parallel = true` steps
  execute as a batch using `ThreadPoolExecutor`.
- `_StepOutcome` internal dataclass; runner loop processes outcome lists
  instead of catching `typer.Exit` from `_run_experiment_step`.
- `experiment.parallel_batch` DEBUG observability event emitted when a
  parallel batch starts.

## [0.18.0] — TBD

### Added
- Self-contained binary RPM for air-gapped RHEL 9 deployment
  (`packaging/build.sh`, `packaging/kvmchaos.spec`).
- Bash completion installed via RPM to `/etc/bash_completion.d/kvmchaos`.
- `build-rpm` GitHub Actions job builds and uploads the RPM on tag push.

### Changed
- `requires-python` lowered from `>=3.14` to `>=3.11` (the actual runtime
  minimum — `tomllib` requires 3.11; no 3.14-specific syntax is used).

## [0.17.0] — 2026-04-24

### Added

- `--json-log PATH` root flag appends structured events as pure JSONL to
  a file alongside the existing stderr stream.

### Changed

- libvirt C-library stderr messages are captured on the
  `kvmchaos.observability.libvirt` logger at DEBUG level instead of
  leaking to fd 2. Visible with `--verbose`.

## [0.16.0] — 2026-04-23

### Added

- `kvmchaos.observability` package with two sinks for inject/revert lifecycle
  events:
  - JSON-formatted log lines on stderr (journald-friendly, `| jq`-pipeable).
  - Synchronous webhook notifier (configurable URL, optional bearer-token
    `Authorization` header, 3 s timeout, per-event subscription filter).
- `[notifier]` section in `~/.config/kvmchaos/config.toml` (`webhook_url`,
  `auth_header`, `timeout_s`, `events`).
- Seven event types: `inject.start`, `inject.success`, `inject.error`,
  `revert.success`, `revert.error`, `experiment.start`, `experiment.end`.
- `--verbose` flag on the root CLI to enable DEBUG-level observability logging.
- `ConfigError` exception for malformed config files (raised at startup).

### Changed

- `_run_step` in `cli.py` now emits observability events alongside the
  existing file-based event log.
- `run` command brackets the experiment with `experiment.start`/`experiment.end`.

## [0.15.0] — 2026-04-23

### Code quality

- Code audit pass: deduplicated net.* `verify()` methods via
  `tc.assert_netem_active`, replaced `inject_cmd` if/elif dispatch with
  `_FAULT_BUILDERS` dict, removed `report_cmd` fast-path hack.
- Moved net fault test mocks from `tc.add_netem_*` down to `subprocess.run`
  (behaviour-level tests robust against tc.py refactors).
- Three bugs fixed: `net.partition` duplicated `_tap_device`; README missing
  `clock.skew`; `NetPacketLossFault` default mismatch (class 50% vs CLI 10%,
  unified to 10%).

### Release engineering

- `__version__` resolves via `importlib.metadata` (was hard-coded stale).
- `CHANGELOG.md` added.
- `ty` wired into dev deps (advisory; `libvirt-python` stubs produce known
  false positives).
- `.github/workflows/release.yml` builds sdist + wheel on tag push.

### Safety envelope

- `~/.config/kvmchaos/config.toml` optional config file with:
  - `[allowlist]` — exact VM names + fnmatch patterns. `--force` overrides.
  - `[rate_limit]` — `injects_per_hour`, `min_interval_between_destructive_seconds`.
- `kvmchaos abort-all` — emergency stop that scans running domains and
  removes any active `netem` qdisc from their tap devices.

### UX

- `kvmchaos run <experiment.toml>` — declarative multi-step chaos runner
  with per-step `continue_on_failure`.
- `kvmchaos doctor` — diagnoses `tc` availability, cgroup v2 mount, libvirt
  group membership, libvirtd reachability, runs dir writability.
- `docs/recipes/` — five worked examples (DB failover, disk-full alerting,
  flaky network, VM restart, memory pressure).
- `docs/examples/config.toml` and `docs/examples/experiment.toml` — annotated
  schema references.
- README troubleshooting section.

## [0.14.0] — 2026-04-23

- `net.corrupt` fault via `tc netem corrupt N%`. Default 1% corruption.
- `NetPacketLossFault` default aligned to 10% (was 50% in class, 10% in CLI).
- `net.partition._tap_device` removed; now uses shared `tc.tap_device`.
- README rewritten with full fault reference including `clock.skew`.

## [0.13.0] — 2026-04-23

- `net.bandwidth` fault via `tc netem rate`. Default 1000 kbps.
- `tap_device()` extracted to `tc.py`; eliminates duplication across net faults.
- Design spec committed documenting `disk.corrupt` as deferred
  (blocked on qcow2 / hot-unplug constraints).

## [0.12.0] — 2026-04-23 (production hardening)

- SIGTERM now triggers revert (not just SIGINT).
- `disk.latency` revert tolerates missing cgroup (QEMU restarted mid-run).
- `vm.freeze` revert restores the original vCPU quota, not a hard-coded `-1`.
- Run records written atomically (tmp file + `os.replace`).
- `del_root_qdisc` is idempotent.
- `--skew` gets explicit bounds (`±31_536_000s`).
- `runs list` skips corrupt records with a warning.
- `--size` upper cap for `disk.fill` (1 TiB).

## [0.11.0]

- HTML report filters: `--since`, `--fault`, `--outcome`, `--vm`.

## [0.10.0]

- `runs list` and `runs show` subcommands.
- Run record atomic writes.

## [0.9.0]

- `clock.skew` fault via QEMU guest agent `setTime`.

## [0.8.0]

- `disk.fill` fault (host-side fill file next to VM image).

## [0.7.0]

- `net.partition` fault.

## [0.6.0]

- `net.packet-loss` fault.

## [0.5.0]

- `kvmchaos report` — self-contained HTML report of run records.

## [0.4.0] — 2026-04-22

- `disk.latency` via cgroup v2 `io.max` (partition→whole-disk resolution).
- `--bandwidth` flag on inject.
- Distinct `dry_run` outcome in run records.

## [0.3.0] — 2026-04-22

- `net.latency` via `tc netem` on host tap device.
- Per-run JSON records under `$XDG_STATE_HOME/kvmchaos/runs/`.
- `local_only` attribute + remote-URI guard.
- `qemu+ssh://` remote libvirt for non-local-only faults.

## [0.2.0]

- `vm.freeze` via scheduler cpu_shares.
- `vm.starve` via virtio-balloon.
- `--dry-run` flag.

## [0.1.0]

- Initial release: `vm.pause`, `vm.kill`.
- CLI: `--version`, `list-vms`, `list-faults`, `inject`.

[Unreleased]: https://github.com/kai/kvmchaos/compare/v0.14.0...HEAD
[0.14.0]: https://github.com/kai/kvmchaos/releases/tag/v0.14.0
[0.13.0]: https://github.com/kai/kvmchaos/releases/tag/v0.13.0
[0.12.0]: https://github.com/kai/kvmchaos/releases/tag/v0.12.0
