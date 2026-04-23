# kvmchaos

Agent-less chaos engineering CLI for KVM/libvirt virtual machines.

Injects reversible faults into VMs from the hypervisor layer via libvirt — no
guest-side agent required. All faults revert automatically after a configurable
hold duration. Linux host only. **Lab use only.**

## Prerequisites

- Fedora / RHEL Linux with libvirt installed and `libvirtd` running
- Python 3.14+
- System packages (Fedora/RHEL): `sudo dnf install libvirt-devel pkg-config iproute`
- User in the `libvirt` group: `sudo usermod -aG libvirt $USER` (re-login required)
- `uv` installed: see https://docs.astral.sh/uv/

Network and disk faults (`net.*`, `disk.*`) require **root or CAP_NET_ADMIN** on
the host because they call `tc` or write to cgroup v2.

## Install

```bash
git clone <repo> kvmchaos && cd kvmchaos
uv sync
uv run kvmchaos --help
```

## Quick Start

```bash
# List running VMs
uv run kvmchaos list-vms

# List available faults
uv run kvmchaos list-faults

# Dry run — prints what would happen, makes no changes
uv run kvmchaos inject vm.pause myvm --dry-run

# Pause a VM for 10 seconds then resume
uv run kvmchaos inject vm.pause myvm --yes --duration 10

# Add 200ms latency to a VM's NIC (requires root)
sudo kvmchaos inject net.latency myvm --yes --delay 200

# Connect to a remote libvirt host
uv run kvmchaos --connect qemu+ssh://host/system inject vm.pause myvm --yes
```

## Faults

| Fault | Description | Requires root |
|---|---|---|
| `vm.pause` | Freeze vCPUs via libvirt suspend | No |
| `vm.kill` | Destroy and restart the VM | No |
| `vm.freeze` | Throttle vCPU quota via scheduler | No |
| `vm.starve` | Shrink guest RAM via virtio-balloon | No |
| `net.latency` | Add one-way delay via `tc netem delay` | Yes |
| `net.packet-loss` | Drop N% of packets via `tc netem loss` | Yes |
| `net.bandwidth` | Cap throughput via `tc netem rate` | Yes |
| `net.corrupt` | Corrupt N% of packets via `tc netem corrupt` | Yes |
| `net.partition` | Block all traffic via `iptables` | Yes |
| `disk.latency` | Throttle disk I/O via cgroup v2 `io.max` | Yes |
| `disk.fill` | Fill disk space with a junk file | No |

All faults run an inject → verify → hold → revert cycle. The run record is written
to `~/.local/state/kvmchaos/runs/` as JSON regardless of outcome.

### Key flags

| Flag | Default | Description |
|---|---|---|
| `--duration N` | 20 | Hold fault for N seconds before reverting |
| `--yes` | — | Skip confirmation prompt |
| `--dry-run` | — | Print plan, make no changes |
| `--delay N` | 200 | Latency in ms (`net.latency`) |
| `--loss N` | 10 | Packet loss % (`net.packet-loss`) |
| `--rate N` | 1000 | Bandwidth cap in kbps (`net.bandwidth`) |
| `--corrupt N` | 1 | Corruption % (`net.corrupt`) |
| `--bandwidth N` | 10 | Disk I/O cap in MB/s (`disk.latency`) |
| `--size N` | 1024 | Fill size in MiB (`disk.fill`) |
| `--skew N` | 3600 | Clock offset in seconds (`clock.skew`) |

## Run Records

Every inject writes a JSON record:

```bash
# List recent runs
uv run kvmchaos runs list

# Show a specific run
uv run kvmchaos runs show <id>

# Generate HTML report
uv run kvmchaos report --output report.html
```

## Platform Notes

- **Primary target:** RHEL 9 KVM host
- **Dev/tested on:** Fedora 43 KVM host
- `disk.latency` requires cgroup v2 (default on RHEL 9, opt-in on RHEL 8)
- `net.*` faults are `local_only` — they must run directly on the KVM host, not via remote libvirt
- `clock.skew` requires `qemu-guest-agent` in the guest

## Development

```bash
uv run pytest                        # run tests
uv run ruff check                    # lint
uv run ruff format --check           # format check
uv run kvmchaos --help               # smoke test
```

## License

MIT.
