# PLAN.md — kvmchaos Roadmap

## v0.1 Scope

Two reversible faults (`vm.pause`, `vm.kill`) via libvirt, agent-less, with
confirmation prompt, JSONL event log, and a Typer CLI.

See `docs/superpowers/specs/2026-04-20-kvmchaos-v0.1-design.md` for the spec.

## Acceptance (v0.1)

- [x] `kvmchaos --version` prints the version
- [x] `kvmchaos list-vms` works without sudo on `qemu:///system`
- [x] `kvmchaos list-faults` lists both faults
- [x] `kvmchaos inject vm.pause <vm>` — inject/verify/revert cycle, all logged
- [x] `kvmchaos inject vm.kill <vm> --yes` — inject/verify/revert cycle, all logged
- [x] Unknown fault / missing VM → exit 2 with helpful message
- [x] `pytest` passes with coverage ≥85%
- [x] `ruff check`, `ruff format --check` clean

## Acceptance (v0.2)

- [x] `vm.freeze` inject/verify/revert cycle logged correctly
- [x] `vm.starve` inject/verify/revert cycle logged correctly
- [x] `--dry-run` prints plan, makes no libvirt mutations, writes no log entries
- [x] `--dry-run` with unknown fault/VM exits 2 with same error message as real run
- [x] `pytest` passes with coverage ≥85%
- [x] `ruff check`, `ruff format --check` clean

## Lab Validation (required after every version)

After automated tests pass, manually test against the lab environment:
**Host:** Fedora 43 KVM · **Guest:** RHEL 9.7 VM

- [ ] `kvmchaos list-vms` shows the RHEL 9.7 VM
- [ ] `kvmchaos inject <fault> <vm> --dry-run` — no prompt, prints plan, no log entry written
- [ ] `kvmchaos inject <fault> <vm>` — full inject/verify/revert cycle completes, JSONL log entry written
- [ ] VM is reachable over SSH after revert (confirm guest recovered)

Run for each new or modified fault. Do not tick acceptance boxes until lab validation passes.

## Backlog (post-v0.1, not scheduled)

- `net.latency` via `tc` (introduces subprocess + privilege)
- `disk.latency` via `dm-delay`
- `migration.abort`
- Structured JSON-per-run records
- HTML report generator
- Remote libvirt (`qemu+ssh://...`)
- Pre-commit hooks, CI

## Decisions Log

| Date       | Decision                                                   | Rationale                                                   |
| ---------- | ---------------------------------------------------------- | ----------------------------------------------------------- |
| 2026-04-20 | Python 3.14 target.                                        | Matches global tooling standard; modern type syntax.        |
| 2026-04-20 | Typer CLI.                                                 | Mainstream, good DX, Click-based.                           |
| 2026-04-20 | `libvirt-python` as libvirt binding.                       | Canonical, still maintained (12.2.0, 2026).                 |
| 2026-04-20 | Fault interface: `inject` + `verify` + `revert` Protocol.  | Matches domain model; Protocol avoids ABC inheritance.      |
| 2026-04-20 | Plugin discovery: explicit registry dict.                  | Two faults don't justify entry points / decorators. YAGNI.  |
| 2026-04-20 | Safety: confirmation prompt + `--yes`. No allowlist.       | Two-VM home lab; allowlist is paperwork.                    |
| 2026-04-20 | Event log: JSONL, stdlib logging only.                     | Greppable, jq-parseable, zero deps.                         |
| 2026-04-20 | Primary test backend: `test:///default`.                   | Real `virDomain` objects without root or qemu.              |
| 2026-04-20 | Coding style C: docstrings everywhere, comments only why.  | Self-teaching artifact without WHAT-narration noise.        |

## Revision Notes

_(Add entries when a decision is reversed or revised, do not delete old rows.)_
