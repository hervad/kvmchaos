# RESUME — kvmchaos Checkpoint

**Saved:** 2026-04-24 (afternoon — v0.17 mid-implementation handoff)
**Status:** v0.16.0 merged + tagged last session. **v0.17.0 is in progress** on
branch `feat/v0.17-clean-streams` (worktree at `.worktrees/v0.17-clean-streams`);
7 of 11 plan tasks fully complete, task 7 awaiting two-stage review, tasks 8–11
untouched. 422 tests passing, ruff clean, working tree clean. No git remote.

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

### v0.17.0 — Clean Observability Streams (IN PROGRESS)

Resolves the v0.16 stderr mixed-stream follow-up.

- **Spec:** `docs/superpowers/specs/2026-04-24-kvmchaos-v0.17-clean-streams-design.md`
- **Plan:** `docs/superpowers/plans/2026-04-24-kvmchaos-v0.17-clean-streams.md` (11 tasks)
- **Branch:** `feat/v0.17-clean-streams`
- **Worktree:** `/home/kai/kvmchaos/.worktrees/v0.17-clean-streams`
- **Driver skill:** `superpowers:subagent-driven-development`
  (fresh subagent per task + two-stage review: spec-compliance then code-quality)

**Task status:**

| # | Task | Impl | Spec review | Code review |
|---|---|---|---|---|
| 1 | version bump + CHANGELOG stub | ✅ `6ee4ec8`+`e887214` | ✅ | ✅ |
| 2 | `json_log_path` on `configure_stderr_logging` | ✅ `21b93b6` | ✅ | ✅ |
| 3 | `_reset_for_tests` closes file handlers | ✅ `7a10da4` | ✅ | ✅ |
| 4 | `--json-log` CLI wiring | ✅ `b64bad2` | ✅ | ✅ |
| 5 | `--json-log` fails fast on unwritable path | ✅ `4f50704`+`917e2a8` | ✅ | ✅ (test-stderr bug fixed) |
| 6 | libvirt error handler | ✅ `a90b8bd` | ✅ | ✅ |
| 7 | idempotent `_register_once` | ✅ `9325dc5` | ⏳ **next** | ⏳ **next** |
| 8 | wire `_register_once` into `connect()` + conftest | — | — | — |
| 9 | end-to-end `--verbose --json-log` capture test | — | — | — |
| 10 | follow-up resolved header + CHANGELOG date + README | — | — | — |
| 11 | final pytest/ruff/coverage + handoff | — | — | — |
| Final | cross-branch code review | — | — | — |

**Resume here next session (in order):**

1. Re-invoke `superpowers:subagent-driven-development`, pointing at the
   plan file. Controller agent is on `main`; subagents work inside the
   `.worktrees/v0.17-clean-streams` worktree.
2. Start with **Task 7 spec review** (target commit `9325dc5` in the
   worktree — check plan Task 7 requirements against the actual diff).
3. Then **Task 7 code-quality review**.
4. Then Tasks 8 → 11 in order, each with implementer → spec reviewer →
   code-quality reviewer cycle. Plan contains complete code blocks and
   expected pre-implementation failure messages for each task.
5. Final: dispatch cross-branch code reviewer; then hand off to user for
   manual **lab validation** (analogous to v0.16's Fedora 43 /
   `qemu:///system` / `server1` test — smoke-test `--json-log PATH` and
   `--verbose` libvirt error capture) before merge + tag `v0.17.0`.

**Deviations already accepted (do not re-flag):**

- Test file imports `Path` from `pathlib` without `# noqa: F401` (ruff
  removed it; `from __future__ import annotations` lets bare `Path`
  forward-references work).
- `test_reset_closes_file_handler` asserts `handler.stream is None` after
  `_reset_for_tests` (not `.closed`) — CPython's `FileHandler.close()`
  nulls the stream before closing.
- `tests/test_libvirt_error_handler.py` omits a `logging` import the plan
  listed — tests don't reference the module directly.
- Task 5's test checks `result.stderr` (not `result.output`) — Click 8.3+
  exposes stderr on `result.stderr` by default; `result.output` is stdout
  only.

**Not scope-reduced / still TODO per plan:**

- Task 8 adds an autouse `_reset_libvirt_registration` fixture to
  `tests/conftest.py` — this prevents cross-test pollution of the
  module-level `_HANDLER_REGISTERED` flag once Task 8 wires registration
  into `connect()`.

## Repo state

- `main` last commit: `37c1801` (spec fix — `libvirt_level` key rename).
- `main` has tag `v0.16.0` (merge commit `fbd2971`).
- Active branch: `feat/v0.17-clean-streams` (9 commits ahead of `main`).
- Worktree HEAD: `9325dc5` (Task 7 implementation).
- Tests: 422 passing, ruff clean, format clean.
- No uncommitted changes in the worktree.

## Known follow-ups

- `docs/superpowers/followups/2026-04-24-observability-stderr-mixed-stream.md`
  — v0.16 stderr interleaves JSON events with libvirt C-lib error lines and
  Typer status messages, so naive `jq .` consumers break. Not blocking;
  webhook sink unaffected. Recommend `--json-log PATH` flag + libvirt error
  handler suppression for a future release.

## What's next (after v0.16.0 lab validation + merge)

- **Phase 5 — Distribution:** PyPI package, shell completion, RPM/DEB specs,
  container image.
- **Phase 6 — Multi-target / Cloud:** multi-VM concurrent experiments,
  ssh-based remote executor, cloud provider backends (AWS/GCP). Needs design.

Each is a focused 1-2 hour session (Phase 6 longer).
