"""`net.latency` fault — inject one-way latency on a VM's first virtual NIC.

Uses ``tc netem`` on the host-side tap device to add a fixed one-way delay.
The tap device name is read from the domain XML ``<target dev="..."/>``
attribute, which libvirt keeps in sync with the running QEMU process.

Requires root or CAP_NET_ADMIN on the host. All other faults are unaffected
by this privilege requirement.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import ClassVar

import libvirt

import kvmchaos.tc as tc

_DELAY_MS: int = 200


class NetLatencyFault:
    """Injects one-way network latency via tc netem on the host tap device.

    Implements the `Fault` protocol — stateless, operates on a provided
    `virDomain` handle.
    """

    name: ClassVar[str] = "net.latency"
    description: ClassVar[str] = f"Add {_DELAY_MS}ms one-way latency to first vNIC via tc netem."
    destructive: ClassVar[bool] = False

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply netem delay to the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_delay(_tap_device(domain), _DELAY_MS)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that a netem qdisc is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem is not present in tc qdisc show output.
        """
        dev = _tap_device(domain)
        output = tc.show_qdisc(dev)
        if "netem" not in output:
            raise RuntimeError(
                f"netem not active on '{dev}' for domain '{domain.name()}' after inject"
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

    Parses the ``<target dev="..."/>`` attribute of the first ``<interface>``
    element in the domain XML descriptor.

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
