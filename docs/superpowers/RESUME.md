# RESUME — kvmchaos v0.1 Execution Checkpoint

**Saved:** 2026-04-20
**Last active skill:** `superpowers:subagent-driven-development`
**Next action:** Execute Task 1 inline.

## What's done

- Brainstorming complete. Design decisions locked in.
- Spec written: [docs/superpowers/specs/2026-04-20-kvmchaos-v0.1-design.md](specs/2026-04-20-kvmchaos-v0.1-design.md)
- Implementation plan written: [docs/superpowers/plans/2026-04-20-kvmchaos-v0.1.md](plans/2026-04-20-kvmchaos-v0.1.md)
- Execution strategy approved (see "Strategy" below).

## What's next

Start Task 1 of the plan. Strategy below.

## Strategy (user-approved, 2026-04-20)

- **Tasks 1, 2, 11 — inline.** Pure scaffolding and quality-gate commands. Subagent overhead outweighs value.
- **Tasks 3-10 — subagent-driven** (implementer → spec reviewer → code-quality reviewer per task, per the `superpowers:subagent-driven-development` skill).
- **Task 12 — hand back to user.** Manual smokes on a real KVM host against a throwaway lab VM.

## Key decisions recap (from spec)

| | |
|---|---|
| Faults | `vm.pause`, `vm.kill` |
| Interface | `Fault` Protocol with `inject`/`verify`/`revert` |
| Registry | explicit dict in `src/kvmchaos/faults/__init__.py` |
| CLI shape | `inject <fault> <vm>`, plus `list-vms`, `list-faults`, `--version` |
| Safety | confirmation prompt + `--yes` bypass (no allowlist) |
| Event log | JSONL via stdlib logging at `$XDG_STATE_HOME/kvmchaos/events.log` |
| Test backend | `test:///default` primary, `MagicMock(spec=…)` only for error paths |
| Python | 3.14+ |
| Deps | `libvirt-python>=12.2.0`, `typer>=0.12`, (dev) `pytest`, `pytest-cov`, `ruff`, `ty` |
| Style | Docstrings on public API; comments only for non-obvious why |

## Resume instructions for next Claude session

1. Read this file and the plan file.
2. Verify `/home/kai/kvmchaos` working tree state — a fresh session may find Task 1 already partially applied if this session got interrupted mid-run.
3. Invoke `superpowers:subagent-driven-development` skill.
4. Begin with Task 1 inline, then follow the strategy above.
5. Commit cadence: one commit per task's final step.

## Current working-tree state

- `/home/kai/kvmchaos/` is otherwise empty — no git init yet, no source files.
- Only `docs/superpowers/{specs,plans,RESUME.md}` exist.
