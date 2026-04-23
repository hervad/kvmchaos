# net.corrupt Fault — Design Spec

**Date:** 2026-04-23
**Status:** Approved

## Overview

Add a `net.corrupt` fault that introduces random bit corruption in a VM's first vNIC
packets via `tc netem corrupt N%` on the host-side tap device. Completes the network
fault set alongside `net.latency` (delay), `net.packet-loss` (drops), and
`net.bandwidth` (throughput cap).

## Fault Behaviour

| Property | Value |
|---|---|
| Name | `net.corrupt` |
| Default corruption | 1% |
| CLI flag | `--corrupt <percent>` (int, min=1, max=100) |
| tc mechanism | `tc qdisc replace dev <dev> root netem corrupt <N>%` |
| `local_only` | `True` |
| `destructive` | `False` |

- **inject:** applies `tc netem corrupt <N>%` on the tap device
- **verify:** checks `tc qdisc show` output contains both `"netem"` and `"corrupt"`
- **revert:** calls `del_root_qdisc` (idempotent since v0.12)

## tc.py Changes

**New function `add_netem_corrupt(dev, corrupt_percent)`** — mirrors `add_netem_loss`
and `add_netem_rate`; runs `tc qdisc replace dev <dev> root netem corrupt <N>%`.

## File Layout

```
src/kvmchaos/
  tc.py                          — add add_netem_corrupt()
  faults/
    __init__.py                  — register NetCorruptFault
    net_corrupt.py               — new fault class
tests/
  test_tc.py                     — add TestAddNetemCorrupt
  test_faults_net_corrupt.py     — new test file
  test_cli.py                    — add TestNetCorruptCli
```

## CLI

`--corrupt` added to `inject_cmd` in `cli.py`:

```python
corrupt: int = typer.Option(
    1,
    "--corrupt",
    help="Packet corruption percentage (net.corrupt only).",
    min=1,
    max=100,
)
```

`net.corrupt` branch in the fault instantiation block:

```python
elif fault_name == "net.corrupt":
    fault = NetCorruptFault(corrupt_percent=corrupt)
```

## Testing

`tests/test_faults_net_corrupt.py` mirrors `test_faults_net_packet_loss.py`:

- Metadata: name, description, non-destructive, local_only, default percent, custom percent
- `inject` calls `add_netem_corrupt` with correct args
- `verify` passes when `show_qdisc` contains `"netem"` and `"corrupt"`
- `verify` raises when `"netem"` absent; raises when `"corrupt"` absent
- `revert` calls `del_root_qdisc`
- `inject` propagates `RuntimeError` from tc
- No-interface error paths

`test_tc.py` — `TestAddNetemCorrupt`:
- calls tc with correct args
- raises `RuntimeError` on non-zero exit

`test_cli.py` — `TestNetCorruptCli`:
- `net.corrupt` appears in `list-faults`
- `--corrupt` flag accepted

## Acceptance Criteria

- [ ] `net.corrupt` registered in `list-faults` with `local_only = True`
- [ ] `kvmchaos inject net.corrupt <vm> --corrupt N` corrupts N% of packets on VM's first vNIC
- [ ] Revert removes the root qdisc, restoring normal forwarding
- [ ] `pytest` passes with coverage ≥85%
- [ ] `ruff check`, `ruff format --check` clean
- [ ] Lab validation on Fedora 43 KVM host
