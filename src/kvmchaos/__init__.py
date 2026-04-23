"""kvmchaos — agent-less chaos engineering for KVM/libvirt VMs."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("kvmchaos")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
