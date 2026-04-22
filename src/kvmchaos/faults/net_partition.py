"""`net.partition` fault — fully sever a VM's network via nftables.

Creates a dedicated nftables table that drops all forwarded traffic on the
VM's host-side tap device. The guest loses all network connectivity for the
duration of the fault. Reverts by deleting the table.

Requires root or CAP_NET_ADMIN on the host. Uses a dedicated
``inet kvmchaos-<dev>`` table so it does not interfere with firewalld.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import ClassVar

import libvirt

import kvmchaos.nft as nft


class NetPartitionFault:
    """Sever a VM's network by dropping all tap device traffic via nftables.

    Implements the ``Fault`` protocol — stateless, operates on a provided
    ``virDomain`` handle.
    """

    name: ClassVar[str] = "net.partition"
    description: ClassVar[str] = "Drop all traffic on first vNIC via nftables (full blackhole)."
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def inject(self, domain: libvirt.virDomain) -> None:
        """Create nftables rules that drop all traffic on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the nft command fails (e.g. permission denied).
        """
        nft.add_partition(_tap_device(domain))

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that the partition table is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If the nftables partition table is not present.
        """
        dev = _tap_device(domain)
        if not nft.partition_active(dev):
            raise RuntimeError(
                f"net.partition not in effect on '{dev}' for domain '{domain.name()}'"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Delete the nftables partition table, restoring normal forwarding.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the nft command fails.
        """
        nft.del_partition(_tap_device(domain))


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
