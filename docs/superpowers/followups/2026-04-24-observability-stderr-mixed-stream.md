# Follow-up: v0.16 observability stderr is a mixed stream

**Status:** Resolved in v0.17.0 — see
`docs/superpowers/specs/2026-04-24-kvmchaos-v0.17-clean-streams-design.md`.

**Filed:** 2026-04-24 (discovered during v0.16.0 lab validation)
**Severity:** Usability gap — not a correctness bug. Webhook sink is unaffected.

## Finding

`kvmchaos --verbose run <experiment.toml> 2>events.jsonl` produces a file
that is *not* pure JSONL. Naive consumers (`jq .`, line-by-line JSON
parsers, log shippers that expect one-JSON-per-line) crash on at least
three kinds of interleaved non-JSON content:

1. **libvirt C-library messages** — e.g.
   `libvirt: Domain Config error : Requested operation is not valid: ...`.
   These are written directly to fd 2 by `libvirt.so` before Python's
   logging pipeline ever sees them.
2. **Typer/CLI human-readable error text** —
   `inject error: Requested operation is not valid: ...` (from
   `typer.echo(..., err=True)` in `cli.py`).
3. **CLI status messages** — `step 1 failed (exit 1); continuing
   (continue_on_failure=true).` and `Experiment finished with N failure(s).`
   (also `typer.echo(..., err=True)`).

## Reproduction

```bash
cat > /tmp/err.toml <<'EOF'
name = "mixed-stream repro"
[[step]]
fault = "vm.pause"
vm = "<a-shutoff-vm>"
duration = 1
continue_on_failure = true
[[step]]
fault = "vm.pause"
vm = "<a-running-vm>"
duration = 1
EOF
uv run kvmchaos --verbose run /tmp/err.toml -y 2>/tmp/events.jsonl
jq . /tmp/events.jsonl          # FAILS at line 3
jq -R 'fromjson? // empty' /tmp/events.jsonl   # works — robust idiom
```

## Current workaround

Document the robust-parse idiom in the README / recipes:

```bash
# Extract only structured events from kvmchaos stderr:
2> >(jq -R 'fromjson? // empty' > events.jsonl)
# or post-hoc:
jq -Rc 'fromjson? // empty' events.jsonl
```

## Fix options (pick one when designing v0.17+)

1. **Dedicated `--json-log PATH` flag.** Opt-in. Writes pure JSONL to the
   specified file while stderr remains the operator-friendly mixed
   stream. Zero breaking change. Cleanest for consumers. ← *Recommended.*
2. **Third file descriptor.** `kvmchaos ... 3>events.jsonl` — clever but
   fragile; non-obvious to new users; breaks under `sh -c` wrappers.
3. **Move human error lines to stdout.** Keeps stderr pure, but stdout
   becomes a mix of narrative and errors — not strictly better.
4. **Suppress libvirt C-lib logs.** `libvirt.virEventRegisterDefaultImpl`
   + `libvirt.registerErrorHandler(lambda ctx, err: None, None)` in
   `libvirt_conn.connect()`. Kills the C-lib noise at the source.
   Compose with option 1 or 3. Does NOT affect Typer echoes.

Combining (1) + (4) gives the cleanest experience: mixed stderr stays
readable for humans, `--json-log` is clean for machines.

## Impact on v0.16.0

None blocking — the webhook sink is unaffected (it receives only the
`emit()` call, never stderr text). Release stands. Track this for the
next observability-touching release.
