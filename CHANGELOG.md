# Changelog

All notable changes to kvmchaos. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are
[semver](https://semver.org/).

## [Unreleased]

- Code audit pass: deduplicated net.* verify() methods via `tc.assert_netem_active`,
  replaced `inject_cmd` if/elif dispatch with `_FAULT_BUILDERS` dict, removed
  `report_cmd` fast-path hack, moved net fault test mocks from `tc.add_netem_*`
  down to `subprocess.run` (behaviour-level tests).
- `__version__` now resolves via `importlib.metadata`, no longer hard-coded.
- `ty` added to dev deps (advisory; libvirt-python stubs surface false positives).

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
