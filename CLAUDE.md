# CLAUDE.md — kvmchaos

Project instructions for Claude. Short by design; the design spec is authoritative.

## Source of truth

- **Spec:** `docs/superpowers/specs/2026-04-20-kvmchaos-v0.1-design.md`
- **Roadmap:** `PLAN.md`
- **Resume pointer:** `docs/superpowers/RESUME.md`

Read both spec and PLAN.md before proposing non-trivial changes.

## Coding standards (level C)

- Docstrings on every public module, class, and function (Google style).
- Inline comments only for non-obvious *why*. Never narrate *what*.
- Type hints on every signature.
- `ruff check` and `ruff format --check` must pass clean.
- No commented-out code. Fail fast; never swallow `libvirtError`.

## Testing

- Primary backend: `test:///default`. Real `virDomain` objects, no root needed.
- Use `MagicMock(spec=libvirt.virDomain)` only for `libvirtError` error paths.
- Coverage target: ≥85%.

## Platform target

Primary: **RHEL 9** KVM host. Dev host: Fedora 43 (functionally identical).
`disk.latency` requires cgroup v2 — default on RHEL 9, opt-in on RHEL 8.
`clock.skew` requires `qemu-guest-agent` in the guest.
All `net.*` faults use `tc netem` — no `br_netfilter` required.

## Dependencies

- Runtime: `libvirt-python`, `typer`. No others without a design change.
- Dev: `pytest`, `pytest-cov`, `ruff`.
- Requires system package: `libvirt-devel` + `pkg-config` (Fedora/RHEL: `dnf install libvirt-devel pkg-config`).

## Commands

```bash
uv run pytest
uv run ruff check && uv run ruff format --check
uv run kvmchaos --help
```
