# Design: JSON Per-Run Records + Remote libvirt

**Date:** 2026-04-22
**Status:** Approved

## Scope

Two independent features implemented in parallel:

1. **JSON per-run records** — one structured JSON file per `inject` invocation, written to `~/.local/state/kvmchaos/runs/`
2. **Remote libvirt** — confirm and test that `--connect qemu+ssh://...` works, add a guard that blocks `net.latency` against remote hosts

These are additive changes. No existing behaviour is removed.

---

## Feature 1: JSON Per-Run Records

### Motivation

The existing JSONL event log appends one line per step (inject / verify / revert). Finding all events for a specific run requires grepping by timestamp. A per-run JSON file groups the full lifecycle of one `inject` invocation into a single, self-contained document — easy to `jq`, easy to feed into a future report generator.

The JSONL log is retained. Both exist side by side and serve different purposes:

| Format | Purpose |
|---|---|
| `events.log` (JSONL) | Streaming audit trail; survives partial runs; grep-friendly |
| `runs/*.json` | Structured per-run summary; easy to parse and report on |

### New module: `src/kvmchaos/runrecord.py`

Responsibilities:
- `default_runs_dir() -> Path` — returns `$XDG_STATE_HOME/kvmchaos/runs/`, defaulting to `~/.local/state/kvmchaos/runs/`
- `write_run_record(record: dict, runs_dir: Path) -> Path` — serialises `record` to `{iso_timestamp}-{fault}-{vm}.json`, creates `runs_dir` if needed, returns the written path

File naming: `{started_at_compact}-{fault}-{vm}.json`, e.g. `20260422T163000Z-vm.freeze-server1.json`. Dots in fault names are replaced with hyphens to avoid ambiguous extensions.

### Run record schema

```json
{
  "started_at": "2026-04-22T16:30:00+00:00",
  "ended_at":   "2026-04-22T16:30:22+00:00",
  "fault":      "vm.freeze",
  "vm":         "server1",
  "uri":        "qemu:///system",
  "dry_run":    false,
  "duration_s": 22,
  "outcome":    "success",
  "steps": [
    {"action": "inject", "result": "ok",   "duration_ms": 12},
    {"action": "verify", "result": "ok",   "duration_ms": 8},
    {"action": "revert", "result": "ok",   "duration_ms": 10}
  ]
}
```

- `outcome`: `"success"` if all steps are `"ok"`, `"fail"` otherwise
- `result` per step: `"ok"` | `"fail"` | `"skipped"` (dry-run)
- Dry-run records are written with `dry_run: true` and all steps as `"skipped"`

### Changes to `cli.py`

`_run_step` gains a return type: a dict with `action`, `result`, `duration_ms`, and optional `error`. It continues logging to JSONL as today.

`inject_cmd` collects the 3 step dicts, constructs the run record, and calls `write_run_record` at the end of the inject lifecycle (after revert, regardless of outcome). The path of the written file is printed to stdout: `Run record: ~/.local/state/kvmchaos/runs/20260422T163000Z-vm.freeze-server1.json`.

### Testing

- `tests/test_runrecord.py` — unit tests for `default_runs_dir`, `write_run_record` (file naming, content schema, dir creation, fault name dot-to-hyphen conversion)
- Integration test in existing CLI test files: run `inject` against `test:///default`, assert the JSON file exists, parses, and has the expected top-level fields

---

## Feature 2: Remote libvirt + net.latency Guard

### Motivation

`--connect` and the `resolve_uri` / `connect()` pipeline already exist and already pass the URI to `libvirt.open()`. Libvirt-python natively supports `qemu+ssh://` URIs. Remote libvirt support is therefore largely already present — what is missing is:

1. Tests that exercise a non-default URI
2. A guard preventing `net.latency` from silently misfiring on a remote host

### Why net.latency is local-only

`net.latency` runs `tc netem` via subprocess on the machine executing kvmchaos. It targets the TAP interface (e.g. `vnet0`) that the KVM hypervisor creates for the guest. That interface only exists on the hypervisor. If kvmchaos runs on a different machine, `tc` operates on the wrong host — no error from libvirt, wrong behaviour.

Workaround: run kvmchaos directly on the KVM host. All VM faults (pause, kill, freeze, starve) work correctly over a remote URI.

### Fault Protocol change

Add `local_only: bool` to the `Fault` Protocol in `src/kvmchaos/faults/__init__.py`.

| Fault | `local_only` |
|---|---|
| `vm.pause` | `False` |
| `vm.kill` | `False` |
| `vm.freeze` | `False` |
| `vm.starve` | `False` |
| `net.latency` | `True` |

### Guard in `inject_cmd`

After resolving the URI and before the confirmation prompt:

```python
def _is_remote(uri: str) -> bool:
    host = urllib.parse.urlparse(uri).hostname or ""
    return host not in ("", "localhost", "127.0.0.1", "::1")
```

If `fault.local_only` is `True` and `_is_remote(resolved_uri)` is `True`:

```
net.latency requires local execution — run kvmchaos directly on the KVM host.
```

Exit code 2 (usage error).

### Testing

- Unit: `_is_remote` with representative local (`""`, `localhost`, `127.0.0.1`, `::1`) and remote (`192.168.1.10`, `hypervisor.local`) inputs
- Unit: `inject_cmd` with a `local_only=True` fault and remote URI → exit 2, correct message
- Unit: `inject_cmd` with a `local_only=False` fault and remote URI → proceeds to connection (mocked)
- Unit: `inject_cmd` with a `local_only=True` fault and local URI → proceeds normally

### Lab verification

`qemu+ssh://localhost/system` exercises the full SSH transport from the KVM host to itself. Requires `ssh-copy-id localhost` to pre-authorize the key.

Lab checklist (to be added to `PLAN.md` after implementation):

- [ ] `kvmchaos --connect qemu+ssh://localhost/system list-vms` shows the RHEL 9.7 VM
- [ ] `kvmchaos --connect qemu+ssh://localhost/system inject vm.pause server1 --yes` completes inject/verify/revert cycle
- [ ] `kvmchaos --connect qemu+ssh://localhost/system inject net.latency server1 --yes` exits 2 with local-only error message
- [ ] Per-run JSON file written to `~/.local/state/kvmchaos/runs/` after each real inject

---

## Decisions

| Decision | Rationale |
|---|---|
| JSONL log retained alongside per-run records | Different consumers: streaming audit vs structured summary |
| Per-run records in `~/.local/state/kvmchaos/runs/` | Consistent with XDG pattern already used by eventlog |
| `local_only` on Protocol, guard in CLI | Faults stay stateless; policy lives at the CLI boundary |
| `_is_remote` uses `urllib.parse` | Stdlib, no deps, handles edge cases (empty host = local socket) |
