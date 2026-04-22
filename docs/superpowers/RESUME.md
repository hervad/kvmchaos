# RESUME — kvmchaos Checkpoint

**Saved:** 2026-04-22
**Status:** v0.4 (disk.latency) code complete; lab validation pending.

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

### v0.4 (unreleased)
- `disk.latency` via cgroup v2 `io.max` (partition→whole-disk resolution)
- `--bandwidth` flag on `inject`
- `outcome="dry_run"` distinct from `"success"` in run records
- `lookupByName` error produces clean exit 2 instead of traceback

## Repo state

- Git branch: `main`
- Tests: 144 passing, 99% coverage
- Ruff: clean; format clean

## What's next

- Lab-validate `disk.latency` on Fedora 43 host + RHEL 9.7 guest,
  then tick the v0.4 acceptance box in `PLAN.md` and tag `v0.4.0`.
- Backlog: `migration.abort`, HTML report generator.
