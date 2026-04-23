# RESUME — kvmchaos Checkpoint

**Saved:** 2026-04-24
**Status:** v0.16.0 implementation complete on `feat/v0.16-observability` branch — lab validation pending before merge to `main`.

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

**Resume here next session:**

1. **Lab validation** of v0.16.0 against real RHEL 9 / Fedora 43 KVM host.
   Smoke test (per design §Acceptance + plan Step 9.7):
   - Set `[notifier].webhook_url = "http://localhost:8000/hook"` in
     `~/.config/kvmchaos/config.toml`.
   - Run a one-shot HTTP listener: `python -m http.server 8000`.
   - `kvmchaos inject vm.pause <real-vm> --duration 5`.
   - Verify stderr shows JSON for `inject.start` → `inject.success` →
     `revert.success`.
   - Verify the listener received three POSTs with matching payloads.
   - Stop the listener, re-run, confirm kvmchaos still completes (notifier
     failure must not propagate).
2. Once lab-validated: append "Lab validation 2026-04-NN passed." to this
   file, then `git checkout main && git merge --no-ff feat/v0.16-observability`
   and tag `v0.16.0`.

## Repo state

- Git branch: `feat/v0.16-observability` (NOT merged to `main`)
- `main` last commit: `f013c19` (v0.15.0)
- Branch HEAD: `98f76e3` (post-final-review fixes)
- Tests: 414 passing, 95% coverage
- Ruff: clean; format clean

## What's next (after v0.16.0 lab validation + merge)

- **Phase 5 — Distribution:** PyPI package, shell completion, RPM/DEB specs,
  container image.
- **Phase 6 — Multi-target / Cloud:** multi-VM concurrent experiments,
  ssh-based remote executor, cloud provider backends (AWS/GCP). Needs design.

Each is a focused 1-2 hour session (Phase 6 longer).
