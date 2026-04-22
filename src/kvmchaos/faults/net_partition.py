"""`net.partition` fault — fully sever a VM's network via tc netem 100% loss.

Uses ``tc netem loss 100%`` on the host-side tap device. This works for
bridge-attached VMs where nftables forward hooks are bypassed by the kernel
bridge layer (``br_netfilter`` not required).

Requires root or CAP_NET_ADMIN on the host.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import ClassVar

import libvirt

import kvmchaos.tc as tc


class NetPartitionFault:
    """Sever a VM's network by setting 100% packet loss via tc netem.

    Implements the ``Fault`` protocol — stateless, operates on a provided
    ``virDomain`` handle.
    """

    name: ClassVar[str] = "net.partition"
    description: ClassVar[str] = "Drop all traffic on first vNIC via tc netem 100% loss."
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def inject(self, domain: libvirt.virDomain) -> None:
        """Set 100% packet loss on the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_loss(_tap_device(domain), 100)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that netem 100% loss is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem or loss is not present in tc qdisc output.
        """
        dev = _tap_device(domain)
        output = tc.show_qdisc(dev)
        if "netem" not in output:
            raise RuntimeError(
                f"net.partition not in effect on '{dev}' for domain '{domain.name()}'"
            )
        if "loss" not in output:
            raise RuntimeError(
                f"net.partition not in effect on '{dev}' for domain '{domain.name()}'"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Remove the root qdisc from the tap device, restoring normal forwarding.

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
