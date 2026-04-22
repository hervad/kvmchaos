"""`net.packet-loss` fault — inject packet loss on a VM's first virtual NIC.

Uses ``tc netem`` on the host-side tap device to drop a fixed percentage of
packets. The tap device name is read from the domain XML ``<target dev="..."/>``
attribute, which libvirt keeps in sync with the running QEMU process.

Requires root or CAP_NET_ADMIN on the host.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import ClassVar

import libvirt

import kvmchaos.tc as tc

_DEFAULT_LOSS_PERCENT: int = 50


class NetPacketLossFault:
    """Injects packet loss via tc netem on the host tap device.

    Implements the ``Fault`` protocol. Stateful: ``loss_percent`` is set at
    construction and used across inject/verify/revert.
    """

    name: ClassVar[str] = "net.packet-loss"
    description: ClassVar[str] = (
        f"Drop {_DEFAULT_LOSS_PERCENT}% of packets on first vNIC via tc netem."
    )
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def __init__(self, loss_percent: int = _DEFAULT_LOSS_PERCENT) -> None:
        """Initialise with a packet-loss percentage.

        Args:
            loss_percent: Percentage of packets to drop (0-100). Default 50.
        """
        self.loss_percent = loss_percent

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply netem packet loss to the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_loss(_tap_device(domain), self.loss_percent)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that netem packet loss is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem is not present or loss is not configured.
        """
        dev = _tap_device(domain)
        output = tc.show_qdisc(dev)
        if "netem" not in output:
            raise RuntimeError(
                f"netem not active on '{dev}' for domain '{domain.name()}' after inject"
            )
        if "loss" not in output:
            raise RuntimeError(
                f"packet loss not active on '{dev}' for domain '{domain.name()}' after inject"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Remove the root qdisc from the tap device, restoring kernel default.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails.
        """
        tc.del_root_qdisc(_tap_device(domain))


def _tap_device(domain: libvirt.virDomain) -> str:
    """Extract the first tap device name from the domain XML.

    Args:
        domain: A live libvirt domain handle.

    Returns:
        Host-side tap device name (e.g. ``'vnet0'``).

    Raises:
        RuntimeError: If no ``<interface>`` with a ``<target dev>`` is found.
    """
    root = ET.fromstring(domain.XMLDesc())
    target = root.find(".//interface/target[@dev]")
    if target is None:
        raise RuntimeError(f"no network interface found for domain '{domain.name()}'")
    return target.attrib["dev"]
