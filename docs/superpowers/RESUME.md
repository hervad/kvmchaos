# RESUME — kvmchaos v0.1 Execution Checkpoint

**Saved:** 2026-04-20 19:33 GMT+2
**Status:** Implementation complete — awaiting user manual smoke tests (Task 12)

## What's done

All 11 automated tasks complete. 42 tests, 93% coverage, ruff clean.

| Task | Status |
|---|---|
| 1 — Repo skeleton (pyproject, git, docs) | ✅ done |
| 2 — Package skeleton + `__version__` | ✅ done |
| 3 — `libvirt_conn.py` | ✅ done |
| 4 — `eventlog.py` | ✅ done |
| 5 — `safety.py` | ✅ done |
| 6 — Fault Protocol (`faults/base.py`) | ✅ done |
| 7 — `vm.pause` fault + conftest | ✅ done |
| 8 — `vm.kill` fault + registry wiring | ✅ done |
| 9 — CLI: `--version`, `list-vms`, `list-faults` | ✅ done |
| 10 — CLI: `inject` command | ✅ done |
| 11 — Quality gates (pytest 93%, ruff clean) | ✅ done |
| 12 — Manual smoke tests on real libvirt host | ⏳ user's turn |

## What's next: Task 12 (user runs these)

```bash
# Confirm libvirt access
virsh -c qemu:///system list --all

# Basics
uv run kvmchaos --version
uv run kvmchaos list-vms
uv run kvmchaos list-faults

# Pause smoke (reversible)
uv run kvmchaos inject vm.pause <vm-name>
cat ~/.local/state/kvmchaos/events.log

# Kill smoke (destructive — throwaway VM only)
uv run kvmchaos inject vm.kill <vm-name> --yes
cat ~/.local/state/kvmchaos/events.log

# Negative cases
uv run kvmchaos inject bogus <vm-name>      # expect exit 2
uv run kvmchaos inject vm.pause no-such-vm  # expect exit 2
```

After smokes pass: flip checkboxes in `PLAN.md`, then `git tag v0.1.0`.

## Repo state

- Git: `main` branch, 13 commits
- Working tree: clean
- `src/kvmchaos/` — all modules implemented
- `tests/` — 42 tests, 93% coverage

## Key files

- Spec: `docs/superpowers/specs/2026-04-20-kvmchaos-v0.1-design.md`
- Plan: `docs/superpowers/plans/2026-04-20-kvmchaos-v0.1.md`
- Plan: `docs/superpowers/plans/2026-04-20-kvmchaos-v0.1.md`
