# disk.latency Fault — Design Spec

## Goal

Add a `disk.latency` fault that throttles a VM's disk I/O to a configurable bandwidth
limit, simulating slow storage (degraded SAN, failing SSD, heavily loaded NFS).

## Background: Why Not dm-delay

The primary VM disk (`/var/lib/libvirt/images/rhel9.7.qcow2`) is a qcow2 file.
dm-delay requires a raw block device and a live disk hotswap — too risky for a chaos
tool (failed revert = VM loses its disk). Instead, this fault uses the Linux blkio
cgroup v2 `io.max` interface, which throttles the QEMU process's I/O at the kernel
level without touching the disk path.

**Trade-off:** This limits throughput (MB/s), not per-operation latency. It will not
trigger fsync-path timeouts on tiny writes, but it will trigger queue depth exhaustion,
connection pool stalls, and backpressure failures — the dominant failure modes for
slow-disk chaos testing.

## Naming

`disk.latency` — describes the observable effect (latency under load), consistent with
`net.latency` which similarly names by effect rather than mechanism.

## Architecture

### New file: `src/kvmchaos/faults/disk_latency.py`

`DiskLatencyFault` class implementing the `Fault` Protocol with:

```
name        = "disk.latency"
description = "Throttle VM disk I/O to <bandwidth> MB/s via blkio cgroup"
destructive = False
local_only  = True   # cgroup writes require local execution + root
```

Unlike the other faults (stateless singletons), `DiskLatencyFault` is instantiated
per inject invocation with `bandwidth_bps: int` set at construction time. The CLI
creates `DiskLatencyFault(bandwidth_bps=bandwidth * 1_000_000)` instead of looking
up a singleton.

### Method: `inject(domain)`

1. Get QEMU PID: read `/var/run/libvirt/qemu/<vm>.pid` (libvirt writes this for every
   running domain). Raises `FileNotFoundError` if VM is not running.
2. Read `/proc/<pid>/cgroup`, extract the path after `0::`.
3. Resolve full cgroup path: `/sys/fs/cgroup/<path>`.
4. Find disk major:minor: iterate `/sys/block/*/dev` to match the device backing
   `/var/lib/libvirt/images/` (read from `virDomain.XMLDesc()` to get the source file,
   then `os.stat(...).st_dev` → `os.major/minor`).
5. Write `{major}:{minor} rbps={bandwidth_bps} wbps={bandwidth_bps}` to
   `<cgroup>/io.max`.

### Method: `verify(domain)`

Re-read `<cgroup>/io.max`, confirm the line for `{major}:{minor}` contains the
expected `rbps` and `wbps` values. Raise `RuntimeError` if not found or values differ.

### Method: `revert(domain)`

Write `{major}:{minor} rbps=max wbps=max` to `<cgroup>/io.max`.

### Cgroup path format

`/proc/<pid>/cgroup` on cgroups v2 contains a single line:
```
0::/machine.slice/machine-qemu\x2d3-server1.scope
```
Full cgroup path: `/sys/fs/cgroup` + the path after `0::`.

### Modified files

- `src/kvmchaos/faults/__init__.py` — add `DiskLatencyFault` to `FAULTS` dict.
  **Special case:** `FAULTS["disk.latency"]` stores the class, not an instance.
  The CLI instantiates it with `bandwidth_bps` when `--bandwidth` is provided.
- `src/kvmchaos/cli.py` — add `--bandwidth` option (default `1`, int, MB/s, `min=1`).
  Before calling `_run_step`, if the selected fault class is `DiskLatencyFault`,
  instantiate it: `fault = fault_cls(bandwidth_bps=bandwidth * 1_000_000)`.
  All other faults remain singletons accessed directly from `FAULTS`.

## CLI

```
kvmchaos inject disk.latency <vm> [--bandwidth N] [--duration D] [--yes] [--dry-run]
```

- `--bandwidth N` — throttle limit in MB/s, default `1`, min `1`
- All other flags (`--duration`, `--yes`, `--dry-run`) work identically to other faults
- `local_only = True` → remote guard blocks with exit 2 automatically

Example:
```bash
sudo env PATH=$PATH uv run kvmchaos inject disk.latency server1 --bandwidth 2 --yes --duration 10
```

## Testing

### `tests/test_disk_latency.py`

- `inject` writes correct `rbps`/`wbps` to `io.max` (mock file I/O, `/proc` read,
  `/var/run/libvirt/qemu/<vm>.pid`, `os.stat`, XML desc)
- `inject` raises if PID file missing
- `inject` raises if disk device not found in `/sys/block`
- `verify` passes when limit matches
- `verify` raises when limit absent or wrong
- `revert` writes `max` to `io.max`
- `DiskLatencyFault(bandwidth_bps=2_000_000)` stores value correctly

### `tests/test_fault_local_only.py`

- `disk.latency` has `local_only = True`

### `tests/test_cli.py`

- `--bandwidth 2` flag is accepted; fault receives `2_000_000` bps

## Acceptance Criteria

- [ ] `disk.latency` appears in `kvmchaos list-faults`
- [ ] `kvmchaos inject disk.latency server1 --bandwidth 2 --yes --duration 10` throttles
      disk I/O (observable: `dd if=/dev/zero of=/tmp/test bs=1M count=100` on guest
      takes ~50s instead of <1s)
- [ ] `kvmchaos inject disk.latency server1 --yes --dry-run` prints plan, writes no
      cgroup entries
- [ ] `kvmchaos --connect qemu+ssh://192.168.0.99/system inject disk.latency server1 --yes`
      exits 2 with `requires local execution`
- [ ] `pytest` passes with coverage ≥85%
- [ ] `ruff check`, `ruff format --check` clean

## Lab Validation

- [ ] `dd` throughput on guest drops to ~2 MB/s during hold, restores after revert
- [ ] `io.max` entry visible in cgroup during hold, cleared after revert
- [ ] Run record written with `outcome: success`

## Decisions

| Decision | Rationale |
|---|---|
| blkio cgroup over dm-delay | qcow2 disk makes dm-delay unsafe for live injection |
| `local_only = True` | cgroup writes require root on the KVM host |
| Instance state for bandwidth | Only `disk.latency` needs per-run config; Protocol unchanged |
| PID from `/var/run/libvirt/qemu/<vm>.pid` | No subprocess, no parsing virsh output |
| `--bandwidth` in MB/s | Human-readable unit; converted to bytes internally |
