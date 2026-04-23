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

## Platform Compatibility

Primary target: **RHEL 9** KVM host. Dev/lab host: Fedora 43 (functionally identical).

| Fault | RHEL 9 | RHEL 8 | Notes |
|---|---|---|---|
| `vm.*`, `net.*`, `clock.skew` | ✅ | ✅ | No special requirements |
| `disk.latency` | ✅ | ⚠️ | Requires cgroup v2; RHEL 8 defaults to v1 — enable with `systemd.unified_cgroup_hierarchy=1` at boot |
| `disk.fill` | ✅ | ✅ | Requires write access to image directory |
| `clock.skew` | ✅ | ✅ | Requires `qemu-guest-agent` in guest |

All `net.*` faults use `tc netem` on the host tap device — no `br_netfilter` or nftables required.

## Lab Validation (required after every version)

After automated tests pass, manually test against the lab environment:
**Dev host:** Fedora 43 KVM · **Primary target:** RHEL 9 KVM · **Guest:** RHEL 9.7 VM

- [x] `kvmchaos list-vms` shows the RHEL 9.7 VM
- [x] `--dry-run` prints plan with no prompt and no log entry (2026-04-22)
- [x] `vm.freeze` — guest sluggish during hold, vcpu_quota=5000 confirmed on host (2026-04-22)
- [x] `vm.starve` — Mem dropped 3.6Gi → 583Mi, swap filled, restored after revert (2026-04-22)
- [x] `vm.pause` — VM completely unresponsive during hold, resumes cleanly (2026-04-22)
- [x] `vm.kill` — VM shuts off, stays down for duration, restarts on revert (2026-04-22)
- [x] `net.latency` — 200ms one-way latency confirmed via ping from server2 (2026-04-22)
- [x] VM reachable over SSH after every revert (2026-04-22)

Run for each new or modified fault. Do not tick acceptance boxes until lab validation passes.

## Acceptance (v0.3)

- [x] `kvmchaos inject vm.pause <vm> --yes --duration 0` writes a `.json` file to `~/.local/state/kvmchaos/runs/`
- [x] `kvmchaos inject vm.pause <vm> --dry-run` writes a record with `dry_run: true` and all steps `skipped`
- [x] `kvmchaos inject net.latency <vm> --connect qemu+ssh://<remote>/system` exits 2 with local-only message
- [x] `kvmchaos inject vm.pause <vm> --connect qemu+ssh://localhost/system --yes --duration 0` completes successfully (requires `ssh-copy-id localhost`)
- [x] `pytest` passes with coverage ≥85%
- [x] `ruff check`, `ruff format --check` clean

## Lab Validation (v0.3)

After automated tests pass, manually test against the lab environment:
**Host:** Fedora 43 KVM · **Guest:** RHEL 9.7 VM

Pre-requisite: `ssh-copy-id localhost` on the KVM host (authorizes key for loopback SSH).

- [x] `kvmchaos --connect qemu+ssh://localhost/system list-vms` shows the RHEL 9.7 VM (2026-04-22)
- [x] `kvmchaos --connect qemu+ssh://localhost/system inject vm.pause server1 --yes --duration 5` completes; run record written to `~/.local/state/kvmchaos/runs/` (2026-04-22)
- [x] `cat` the run record — JSON parses, `outcome: success`, 3 steps all `ok` (2026-04-22)
- [x] `uv run kvmchaos --connect qemu+ssh://192.168.0.99/system inject net.latency server1 --yes` exits 2 with `requires local execution` (2026-04-22)
- [x] `kvmchaos inject vm.pause server1 --yes --dry-run` writes a record with `dry_run: true` (2026-04-22)

Run for each new or modified feature. Do not tick acceptance boxes until lab validation passes.

## Acceptance (v0.4)

- [x] `disk.latency` registered in `list-faults` with `local_only = True`
- [x] `kvmchaos inject disk.latency <vm> --bandwidth N` throttles VM disk I/O to N MB/s via cgroup v2 `io.max`
- [x] `disk.latency` resolves partition `major:minor` to whole-disk before writing `io.max`
- [x] Revert writes `rbps=max wbps=max` to restore full I/O
- [x] `pytest` passes with coverage ≥85%
- [x] `ruff check`, `ruff format --check` clean
- [x] Lab validation on Fedora 43 KVM host (2026-04-22)

## Acceptance (v0.5)

- [x] `kvmchaos report` reads run records under `$XDG_STATE_HOME/kvmchaos/runs/`
      and writes a self-contained HTML file (default `./kvmchaos-report.html`)
- [x] `--output PATH` and `--runs-dir DIR` options respected
- [x] Empty runs dir produces valid HTML with a "No runs" message, exit 0
- [x] Summary header shows total, success / fail / dry_run counts, date range
- [x] Table columns: `started_at`, `fault`, `vm`, `outcome`, `duration_s`,
      `dry_run`; each row has an expandable `<details>` with the steps JSON
- [x] `pytest` passes with coverage ≥85%
- [x] `ruff check`, `ruff format --check` clean

## Acceptance (v0.6)

- [x] `kvmchaos runs list` prints `No runs.` on an empty directory, exit 0
- [x] `kvmchaos runs list` prints a newest-first table with columns
      `id`, `started_at`, `fault`, `vm`, `outcome`, `duration_s`
- [x] `--limit N` caps the number of rows
- [x] `--runs-dir DIR` honoured on both `list` and `show`
- [x] `kvmchaos runs show <id>` prints the record as indented JSON
- [x] Unambiguous id prefix accepted; ambiguous prefix exits 2 with candidates
- [x] Unknown id exits 2 with a helpful message
- [x] `pytest` passes with coverage ≥85%
- [x] `ruff check`, `ruff format --check` clean

## Acceptance (v0.7)

- [x] `--since ISO`, `--fault NAME`, `--outcome NAME`, `--vm NAME` accepted
      on both `kvmchaos report` and `kvmchaos runs list`
- [x] `--since` accepts both date-only (`2026-04-22`) and full datetime
      (`2026-04-22T12:00:00+00:00`); naive values are treated as UTC
- [x] Filters compose (AND); an empty result renders "No runs." or a
      valid empty-state HTML page, exit 0
- [x] Invalid `--since` value exits non-zero with a helpful message
- [x] `--limit` is applied AFTER filtering on `runs list`
- [x] `pytest` passes with coverage ≥85%
- [x] `ruff check`, `ruff format --check` clean

## Acceptance (v0.8)

- [x] `disk.fill` registered in `list-faults` with `local_only = True`
- [x] `kvmchaos inject disk.fill <vm> --size N` creates a fill file of N MiB next to the VM image
- [x] Fill file placed at `<image-dir>/.kvmchaos-fill-<vm>` on the host filesystem
- [x] Revert deletes the fill file; revert is idempotent (no error if already gone)
- [x] `pytest` passes with coverage ≥85%
- [x] `ruff check`, `ruff format --check` clean
- [x] Lab validation on Fedora 43 KVM host (2026-04-23)

## Acceptance (v0.9)

- [x] `net.packet-loss` registered in `list-faults` with `local_only = True`
- [x] `kvmchaos inject net.packet-loss <vm> --loss N` drops N% of packets via tc netem
- [x] `--loss` defaults to 50; accepted range 1-100
- [x] Revert removes the root qdisc, restoring kernel default
- [x] `pytest` passes with coverage >=85%
- [x] `ruff check`, `ruff format --check` clean
- [x] Lab validation on Fedora 43 KVM host (2026-04-23) — 37-59% loss observed at 50% target (netem random model; variance expected on small samples)

## Acceptance (v0.10)

- [x] `clock.skew` registered in `list-faults` with `local_only = False`
- [x] `kvmchaos inject clock.skew <vm> --skew N` shifts guest clock by N seconds (negative = backward)
- [x] `--skew` defaults to 3600 (1 hour forward)
- [x] Revert resets guest clock to host wall clock time
- [x] Requires `qemu-guest-agent` running in the guest
- [x] `pytest` passes with coverage >=85%
- [x] `ruff check`, `ruff format --check` clean
- [x] Lab validation on Fedora 43 KVM host (2026-04-23) — clock jumped 01:37→02:38, restored to 01:38 on revert

## Acceptance (v0.11)

- [x] `net.partition` registered in `list-faults` with `local_only = True`
- [x] `kvmchaos inject net.partition <vm> --yes` drops all traffic on first vNIC via tc netem 100% loss
- [x] Revert removes root qdisc, restoring normal forwarding
- [x] Works with bridged VMs (no br_netfilter required)
- [x] `pytest` passes with coverage >=85%
- [x] `ruff check`, `ruff format --check` clean
- [x] Lab validation on Fedora 43 KVM host (2026-04-23) — seq 9-23 "Destination Host Unreachable", restored at seq 24

## Acceptance (v0.12) — Production Hardening

Findings from production readiness audit (2026-04-23). Prioritised for RHEL 9 production use.

### HIGH — could leave VMs broken indefinitely

- [ ] **SIGTERM triggers revert** (`cli.py`) — install `signal.SIGTERM` handler that raises
      `KeyboardInterrupt` so the `finally` block fires on systemd stop / `kill <pid>`
- [ ] **`disk.latency` revert tolerates missing cgroup** (`disk_latency.py`) — if QEMU restarts
      between inject and revert, the cgroup PID changes and `_io_max_path()` raises
      `FileNotFoundError`; revert must not leave the throttle in place
- [ ] **`vm.freeze` revert restores original quota** (`vm_freeze.py`) — hard-codes `-1`
      (unlimited); must read and save the pre-inject vCPU quota and restore it on revert

### MEDIUM — operational rough edges

- [ ] **Atomic run record writes** (`runrecord.py:168`) — `write_text()` is not atomic;
      a mid-write kill leaves a corrupt JSON that breaks `runs list`; use `.tmp` + `os.replace()`
- [ ] **`del_root_qdisc` tolerates missing qdisc** (`tc.py`) — raises if no qdisc exists
      (e.g. inject failed halfway); revert should be idempotent like `disk.fill.revert`
- [ ] **`--skew` bounds validation** (`cli.py`) — no `min`/`max`; `--skew 0` is a silent
      no-op; extreme values go unchecked; add `min=-86400*365`, `max=86400*365` or similar

### LOW

- [ ] **`runs list` skips corrupt records** (`cli.py`) — `record["started_at"]` KeyError on
      hand-edited or truncated files; use `.get()` with a skip-and-warn fallback
- [ ] **`--size` upper cap for `disk.fill`** (`cli.py`) — no upper bound; absurd values
      (e.g. `--size 2147483647`) attempt a 2 PiB allocation

## Backlog (post-v0.11, not scheduled)

- `disk.corrupt` — targeted block-level corruption (high risk, needs design)
- `migration.abort` — deferred; requires a second KVM host (or a nested-KVM
  lab setup) to produce an in-flight migration to cancel. Revisit when the
  lab grows beyond a single hypervisor.

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

| Date       | Revised decision                                           | Rationale                                                   |
| ---------- | ---------------------------------------------------------- | ----------------------------------------------------------- |
| 2026-04-22 | `disk.latency` uses cgroup v2 `io.max`, not `dm-delay`.    | dm-delay is unsafe to live-inject on a qcow2-backed disk.   |
| 2026-04-23 | Defer `migration.abort` past v0.5.                         | Single-host lab cannot produce an in-flight migration.      |
