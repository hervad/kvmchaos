# RESUME — kvmchaos Checkpoint

**Saved:** 2026-04-23
**Status:** v0.13 (net.bandwidth) complete and lab-validated.

## What's done

### v0.1 (tag v0.1.0)
- Repo skeleton, `libvirt_conn`, `eventlog`, `safety`
- `vm.pause`, `vm.kill`
- CLI: `--version`, `list-vms`, `list-faults`, `inject`

### v0.2 (tag v0.2.0)
- `vm.freeze` via scheduler `cpu_shares`
- `vm.starve` via virtio-balloon
- `--dry-run`

### v0.3 (tag v0.3.0)
- `net.latency` via `tc netem` on host tap
- Per-run JSON records under `$XDG_STATE_HOME/kvmchaos/runs/`
- `local_only` attribute + remote-URI guard for tap/cgroup faults
- `qemu+ssh://` remote libvirt works for non-local-only faults

### v0.4–v0.12 (unreleased bundle)
- `disk.latency` via cgroup v2 `io.max`
- `disk.fill`, `net.packet-loss`, `net.partition`, `vm.starve`
- HTML report generator (`kvmchaos report`)
- Run records: atomic writes, corrupt-record skip, `dry_run` outcome
- Production hardening: SIGTERM revert, idempotent `del_root_qdisc`, bounds validation

### v0.13 (unreleased)
- `net.bandwidth` via `tc netem rate` on host tap device
- `--rate <kbps>` flag on `inject`
- `tap_device()` extracted to `tc.py` (no duplication across net fault files)
- Lab-validated: inject/verify/revert all `ok`, outcome `success` (2026-04-23)

## Repo state

- Git branch: `main`
- Tests: 310 passing, 98% coverage
- Ruff: clean; format clean

## What's next

- Tag `v0.13.0` (or roll into a larger release tag).
- Backlog: `disk.corrupt`, `migration.abort`, HTML report enhancements.
