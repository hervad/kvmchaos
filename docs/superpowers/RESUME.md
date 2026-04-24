# RESUME — kvmchaos Checkpoint

**Saved:** 2026-04-25 (morning — v0.18.0 lab validated on RHEL 9)
**Status:** v0.18.0 complete. RPM installs on RHEL 9 with no Python dependency.
424 tests, 95% coverage, ruff clean. No open work items.

## What's done

### v0.1 → v0.12 (legacy — see CHANGELOG)

Foundational faults, run records, HTML report, production hardening.

### v0.13.0 — `net.bandwidth`

`tc netem rate`; `tap_device()` extracted to `tc.py`.

### v0.14.0 — `net.corrupt`

`tc netem corrupt`; all 12 faults now shipped.

### v0.15.0

**Code audit & refactor**
- `tc.assert_netem_active` consolidates five duplicate `verify()` methods.
- `_FAULT_BUILDERS` dict replaces `inject_cmd` if/elif chain.
- Net fault tests now mock at `subprocess.run` (behaviour-level).
- Three audit bugs fixed (`net_partition`, README gap, packet-loss default).

**Release engineering**
- `__version__` via `importlib.metadata`.
- `CHANGELOG.md` with full history.
- `ty` wired as advisory type checker.
- `.github/workflows/release.yml` for tag-driven sdist+wheel builds.

**Safety envelope**
- `~/.config/kvmchaos/config.toml` with `[allowlist]` and `[rate_limit]`.
- `kvmchaos abort-all` emergency stop.
- `--force` to bypass safety rails on demand.

**UX**
- `kvmchaos run <experiment.toml>` — declarative multi-step chaos.
- `kvmchaos doctor` — env diagnostic.
- Five recipes in `docs/recipes/`.
- README troubleshooting table.

### v0.16.0 (last session — implementation done, lab validation pending)

Branch: `feat/v0.16-observability` (14 commits, NOT yet merged to `main`).
Spec: `docs/superpowers/specs/2026-04-23-kvmchaos-v0.16-observability-design.md`
Plan: `docs/superpowers/plans/2026-04-23-kvmchaos-v0.16-observability.md`

**Observability (Phase 4)**
- New `kvmchaos.observability` package: `events`, `logging`, `notifier`,
  `emit` fan-out, plus `__init__` re-exporting the public surface.
- Seven events emitted from `_run_step` and `run_cmd`:
  `inject.start/success/error`, `revert.success/error`,
  `experiment.start/end`.
- `experiment.end` reports `status="partial"` when `continue_on_failure`
  absorbs step failures (caught by final review, fixed in `98f76e3`).
- `[notifier]` config section + `ConfigError` validation in `config.py`.
- `--verbose` on root CLI for DEBUG observability logs.
- Prometheus `/metrics` and Slack-native formatting deferred (see spec §6).

**Lab validation 2026-04-24 passed** on Fedora 43 / `qemu:///system`, VM `server1`:

- Run 1 (listener up, duration=5s): exit 0. Stderr emitted three INFO JSON
  events (`inject.start` → `inject.success` → `revert.success`). The local
  sink at `http://127.0.0.1:8000/hook` received three POSTs with bodies
  matching the stderr payloads (`event`, `fault=vm.pause`, `vm=server1`,
  `elapsed_s`, etc.). All POSTs returned HTTP 200.
- Run 2 (listener down, duration=3s): exit 0. Stderr emitted the same three
  INFO events interleaved with three WARNING lines
  (`notifier: transport error ... [Errno 111] Connection refused`). Fault
  was injected and reverted cleanly; notifier failure did not propagate.

Artefacts:

- Config used: `~/.config/kvmchaos/config.toml` with
  `[notifier] webhook_url = "http://127.0.0.1:8000/hook"`.
- Run records: `~/.local/state/kvmchaos/runs/20260424T094529Z-...json` and
  `20260424T094606Z-...json`.
- Capture script: `/tmp/kvmchaos-lab/hook_server.py` (logs POST bodies to
  `hook.log`).

**v0.16 resume points (still valid, lower priority):**

1. If a GitHub remote is added: `git remote add origin <url>`, then
   `git push origin main` + `git push origin v0.16.0` — the existing
   `.github/workflows/release.yml` will build sdist+wheel on the tag.
2. Optionally delete the local `feat/v0.16-observability` branch once
   you're sure you don't need to cherry-pick from it.

---

### v0.17.0 — Clean Observability Streams

Resolves the v0.16 stderr mixed-stream follow-up.

- **Spec:** `docs/superpowers/specs/2026-04-24-kvmchaos-v0.17-clean-streams-design.md`
- **Plan:** `docs/superpowers/plans/2026-04-24-kvmchaos-v0.17-clean-streams.md` (11 tasks)
- **Branch:** `feat/v0.17-clean-streams` — **13 commits, HEAD `55917d1`**
- **Worktree:** `/home/kai/kvmchaos/.worktrees/v0.17-clean-streams`

**Task status — all complete:**

| # | Task | Impl | Spec review | Code review |
|---|---|---|---|---|
| 1 | version bump + CHANGELOG stub | ✅ `6ee4ec8`+`e887214` | ✅ | ✅ |
| 2 | `json_log_path` on `configure_stderr_logging` | ✅ `21b93b6` | ✅ | ✅ |
| 3 | `_reset_for_tests` closes file handlers | ✅ `7a10da4` | ✅ | ✅ |
| 4 | `--json-log` CLI wiring | ✅ `b64bad2` | ✅ | ✅ |
| 5 | `--json-log` fails fast on unwritable path | ✅ `4f50704`+`917e2a8` | ✅ | ✅ |
| 6 | libvirt error handler | ✅ `a90b8bd` | ✅ | ✅ |
| 7 | idempotent `_register_once` | ✅ `9325dc5` | ✅ | ✅ |
| 8 | wire `_register_once` into `connect()` + conftest | ✅ `c925e0d`+`545675d` | ✅ | ✅ |
| 9 | end-to-end `--verbose --json-log` capture test | ✅ `f590568` | ✅ | ✅ |
| 10 | follow-up resolved header + CHANGELOG date + README | ✅ `55917d1` | ✅ | ✅ |
| 11 | final pytest/ruff/coverage + handoff | ✅ | — | — |
| Final | cross-branch code review | ✅ APPROVED | — | — |

**Lab validation 2026-04-24 passed** on Fedora 43 / `qemu:///system`, VM `server1`
(domain not running — exercised the inject.error path):

- Run 1 (`--json-log` only): exit non-zero (domain not running). JSONL file parsed
  cleanly with `jq .` — four structured records, no raw libvirt C-lib text.
- Run 2 (`--verbose --json-log`): same outcome plus one `libvirt.stderr` DEBUG event
  in the JSONL file (`event`, `code`, `domain`, `libvirt_level` all present). Pure
  JSONL throughout — original mixed-stream bug is resolved.

## Repo state

- `main` HEAD: `b0f98e8` (packaging: drop bash completion from RPM).
- Tags: `v0.16.0` (`fbd2971`), `v0.17.0` (`323a2e8`), `v0.18.0` (`b0f98e8`).
- GitHub remote: `https://github.com/hermanvadym/kvmchaos` (private).
- Tests: 424 passing, 95% coverage, ruff clean, format clean.

## Known follow-ups

- **Resolved in v0.17.0:** `docs/superpowers/followups/2026-04-24-observability-stderr-mixed-stream.md`
  — the `--json-log` flag and libvirt error handler were implemented. The follow-up
  doc has been marked resolved.

## What's next

- **v0.18 lab validation PASSED** on RHEL 9 (`server1`, 192.168.122.95):
  `sudo rpm -i kvmchaos-0.18.0-1.el9.x86_64.rpm` installed cleanly,
  `kvmchaos --version` returned `0.18.0`. No Python on host required.
  Note: bash completion dropped (CLI has `add_completion=False`).
- **Phase 6 — Multi-target / Cloud:** multi-VM concurrent experiments,
  ssh-based remote executor, cloud provider backends (AWS/GCP). Needs design.

Each is a focused 1-2 hour session (Phase 6 longer).
