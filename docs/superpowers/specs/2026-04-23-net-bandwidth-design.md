# net.bandwidth Fault — Design Spec

**Date:** 2026-04-23
**Status:** Approved

## Overview

Add a `net.bandwidth` fault that caps a VM's first vNIC throughput to N kbps via
`tc netem rate` on the host-side tap device. Rounds out the network fault set alongside
`net.latency` (delay) and `net.packet-loss` (drops).

## Fault Behaviour

| Property | Value |
|---|---|
| Name | `net.bandwidth` |
| Default rate | 1000 kbps (1 Mbps) |
| CLI flag | `--rate <kbps>` (min=1, int) |
| tc mechanism | `tc qdisc replace dev <dev> root netem rate <N>kbit` |
| `local_only` | `True` |
| `destructive` | `False` |

- **inject:** applies `tc netem rate <N>kbit` on the tap device
- **verify:** checks `tc qdisc show` output contains both `"netem"` and `"rate"`
- **revert:** calls `del_root_qdisc` (idempotent since v0.12)

## tc.py Changes

1. **New function `add_netem_rate(dev, rate_kbps)`** — mirrors `add_netem_delay` and
   `add_netem_loss`; runs `tc qdisc replace dev <dev> root netem rate <N>kbit`.

2. **Extract `_tap_device` into `tc.py` as a public function** — currently duplicated
   verbatim in `net_latency.py` and `net_packet_loss.py`. Moving it to `tc.py` removes
   the duplication (three copies would exist once `net_bandwidth.py` is added).
   Both existing files are updated to import `tap_device` from `kvmchaos.tc`.

## File Layout

```
src/kvmchaos/
  tc.py                          — add add_netem_rate(), tap_device()
  faults/
    __init__.py                  — register NetBandwidthFault
    net_bandwidth.py             — new fault class
    net_latency.py               — import tap_device from tc, remove local copy
    net_packet_loss.py           — import tap_device from tc, remove local copy
tests/
  test_tc.py                     — add TestAddNetemRate
  test_faults_net_bandwidth.py   — new test file
  test_faults_net_latency.py     — update tap_device import
  test_faults_net_packet_loss.py — update tap_device import
```

## CLI

`--rate` added to `inject_cmd` in `cli.py`:

```python
rate: int = typer.Option(
    1000,
    "--rate",
    help="Bandwidth cap in kbps (net.bandwidth only).",
    min=1,
)
```

`net.bandwidth` branch in the fault instantiation block:

```python
elif fault_name == "net.bandwidth":
    fault = NetBandwidthFault(rate_kbps=rate)
```

## Testing

`tests/test_faults_net_bandwidth.py` mirrors `test_faults_net_packet_loss.py`:

- Metadata: name, description, non-destructive, local_only, default rate, custom rate
- `inject` calls `add_netem_rate` with correct args
- `verify` passes when `show_qdisc` contains `"netem"` and `"rate"`
- `verify` raises when `"netem"` absent; raises when `"rate"` absent
- `revert` calls `del_root_qdisc`
- `inject` propagates `RuntimeError` from tc

`test_tc.py` — `TestAddNetemRate`:
- calls tc with correct args
- raises `RuntimeError` on non-zero exit

## Acceptance Criteria

- [ ] `net.bandwidth` registered in `list-faults` with `local_only = True`
- [ ] `kvmchaos inject net.bandwidth <vm> --rate N` caps VM NIC throughput to N kbps
- [ ] Revert removes the root qdisc, restoring normal forwarding
- [ ] `_tap_device` extracted to `tc.py`; no duplication across net fault files
- [ ] `pytest` passes with coverage ≥85%
- [ ] `ruff check`, `ruff format --check` clean
- [ ] Lab validation on Fedora 43 KVM host
