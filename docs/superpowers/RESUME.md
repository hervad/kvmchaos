# RESUME — kvmchaos v0.2 Execution Checkpoint

**Saved:** 2026-04-21
**Status:** v0.2.0 complete and tagged — ready for next feature cycle

## What's done

### v0.1 (tagged v0.1.0)
- Repo skeleton, package, libvirt_conn, eventlog, safety
- `vm.pause` and `vm.kill` faults
- CLI: `--version`, `list-vms`, `list-faults`, `inject`
- 42 tests, 93% coverage, ruff clean

### v0.2 (tagged v0.2.0)
- `vm.freeze` — CPU scheduler throttle via `schedulerParameters()` / `setSchedulerParameters()`
- `vm.starve` — balloon memory squeeze via `setMemory()` / `memoryStats()`
- `--dry-run / -n` flag on `inject` — full validation, no mutation, no log writes
- 70 tests total, 94% coverage, ruff clean

## Repo state

- Git: `main` branch, 20 commits
- Working tree: clean
- Latest tag: `v0.2.0` at `28f1345`

## Key files

| File | Purpose |
|---|---|
| `src/kvmchaos/faults/vm_freeze.py` | CPU throttle fault |
| `src/kvmchaos/faults/vm_starve.py` | Memory balloon fault |
| `src/kvmchaos/cli.py` | inject_cmd + _run_step with --dry-run |
| `tests/test_faults_vm_freeze.py` | 10 tests, all mock-based |
| `tests/test_faults_vm_starve.py` | 11 tests, all mock-based |
| `tests/test_cli_dry_run.py` | 7 CLI integration tests |

## Important implementation notes

- `vm.freeze` uses `domain.schedulerParameters()` / `domain.setSchedulerParameters()` — NOT `getCpuSchedulerParameters` (which doesn't exist in libvirt-python)
- `vm.starve` reads `maxMemory()` fresh at each step — no instance state needed
- Both faults use `MagicMock(spec=libvirt.virDomain)` for all tests — `test:///default` doesn't support QEMU-specific scheduler or balloon APIs
- `vm.freeze` revert hardcodes `cpu_shares=1024` (QEMU/KVM default) — pre-inject value is not preserved

## What's next

Backlog (from PLAN.md):
- `net.latency` via `tc` (introduces subprocess + privilege)
- `disk.latency` via `dm-delay`
- `migration.abort`
- Structured JSON-per-run records
- HTML report generator
- Remote libvirt (`qemu+ssh://...`)
