# kvmchaos

Agent-less chaos engineering CLI for KVM/libvirt virtual machines.

Injects reversible faults (`vm.pause`, `vm.kill`) into VMs from the hypervisor
layer via libvirt. No guest-side agent. Linux host only. **Lab use only.**

## Prerequisites

- Fedora / RHEL / Debian-based Linux with libvirt installed and `libvirtd` running.
- Python 3.14+.
- System packages (Fedora): `sudo dnf install libvirt-devel pkg-config`.
- User in the `libvirt` group: `sudo usermod -aG libvirt $USER` (re-login required).
- `uv` installed: see https://docs.astral.sh/uv/.

## Install (from source)

```bash
git clone <repo> kvmchaos && cd kvmchaos
uv sync
```

## Usage

```bash
uv run kvmchaos --version
uv run kvmchaos list-vms
uv run kvmchaos list-faults
uv run kvmchaos inject vm.pause <vm-name>
uv run kvmchaos inject vm.kill  <vm-name> --yes
```

Connection URI precedence: `--connect` flag > `$LIBVIRT_DEFAULT_URI` > `qemu:///system`.

## Warnings

- `vm.pause` freezes vCPUs but keeps RAM. Guest clocks drift while paused.
- `vm.kill` destroys the running guest gracefully (SIGTERM then SIGKILL).
  Unsaved guest state is lost. `revert` starts the VM from its defined config.
- This tool is **not** production-safe. Do not point it at anything you care about.

## Development

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
```

## License

MIT.
