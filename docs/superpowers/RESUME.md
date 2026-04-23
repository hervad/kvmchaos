# RESUME — kvmchaos Checkpoint

**Saved:** 2026-04-23
**Status:** v0.16.0 — observability (journald JSON + webhook notifier).

## What's done

### v0.1 → v0.12 (legacy — see CHANGELOG)

Foundational faults, run records, HTML report, production hardening.

### v0.13.0 — `net.bandwidth`

`tc netem rate`; `tap_device()` extracted to `tc.py`.

### v0.14.0 — `net.corrupt`

`tc netem corrupt`; all 12 faults now shipped.

### v0.15.0 (this session)

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

### v0.16.0 (this session)

**Observability (Phase 4)**
- New `kvmchaos.observability` package: stderr JSON logger + webhook `Notifier`.
- Seven events emitted from `_run_step` and `run_cmd`.
- `[notifier]` section + `ConfigError` validation in `config.py`.
- `--verbose` on root CLI for DEBUG observability logs.
- Prometheus `/metrics` and Slack-native formatting deferred (see spec §6).

## Repo state

- Git branch: `main`
- Tests: 386 passing, 95% coverage
- Ruff: clean; format clean
- `ty` advisory: 9 pre-existing libvirt-stub false positives

## What's next

- **Phase 5 — Distribution:** PyPI package, shell completion, RPM/DEB specs,
  container image.
- **Phase 6 — Multi-target / Cloud:** multi-VM concurrent experiments,
  ssh-based remote executor, cloud provider backends (AWS/GCP). Needs design.

Each is a focused 1-2 hour session (Phase 6 longer).
