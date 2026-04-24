# RESUME — kvmchaos Checkpoint

**Saved:** 2026-04-24
**Status:** v0.16.0 merged to local `main` (merge commit `fbd2971`) and tagged `v0.16.0`. No git remote is configured, so nothing was pushed and the release workflow did not run.

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

**Resume here next session:**

1. If a GitHub remote is being added: `git remote add origin <url>`, then
   `git push origin main` + `git push origin v0.16.0` — the existing
   `.github/workflows/release.yml` will build sdist+wheel on the tag.
2. Optionally delete the local `feat/v0.16-observability` branch once
   you're sure you don't need to cherry-pick from it.
3. Otherwise start Phase 5 (Distribution) — see "What's next" below.

## Repo state

- Git branch: `feat/v0.16-observability` (NOT merged to `main`)
- `main` last commit: `f013c19` (v0.15.0)
- Branch HEAD: `98f76e3` (post-final-review fixes)
- Tests: 414 passing, 95% coverage
- Ruff: clean; format clean

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
