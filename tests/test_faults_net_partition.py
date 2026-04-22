"""Tests for net.partition fault."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import libvirt
import pytest

import kvmchaos.tc as tc
from kvmchaos.faults.net_partition import NetPartitionFault

_XML = """
<domain>
  <devices>
    <interface type='network'>
      <target dev='vnet0'/>
    </interface>
  </devices>
</domain>
"""

_XML_NO_IFACE = "<domain><devices></devices></domain>"


def _mock_domain(xml: str = _XML) -> MagicMock:
    domain = MagicMock(spec=libvirt.virDomain)
    domain.name.return_value = "server1"
    domain.XMLDesc.return_value = xml
    return domain


class TestNetPartitionMetadata:
    def test_name(self):
        assert NetPartitionFault.name == "net.partition"

    def test_description_present(self):
        assert NetPartitionFault.description

    def test_non_destructive(self):
        assert NetPartitionFault.destructive is False

    def test_local_only(self):
        assert NetPartitionFault.local_only is True


class TestNetPartitionHappyPath:
    def test_inject_sets_100_percent_loss(self):
        domain = _mock_domain()
        with patch.object(tc, "add_netem_loss") as mock_add:
            NetPartitionFault().inject(domain)
        mock_add.assert_called_once_with("vnet0", 100)

    def test_verify_passes_when_netem_loss_present(self):
        domain = _mock_domain()
        with patch.object(
            tc, "show_qdisc", return_value="qdisc netem 8001: root refcnt 2 loss 100%"
        ):
            NetPartitionFault().verify(domain)  # must not raise

    def test_verify_raises_when_netem_absent(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "show_qdisc", return_value="qdisc pfifo_fast 0: root"),
            pytest.raises(RuntimeError, match=r"net\.partition not in effect"),
        ):
            NetPartitionFault().verify(domain)

    def test_verify_raises_when_loss_absent(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "show_qdisc", return_value="qdisc netem 8001: root delay 200ms"),
            pytest.raises(RuntimeError, match=r"net\.partition not in effect"),
        ):
            NetPartitionFault().verify(domain)

    def test_revert_calls_del_root_qdisc(self):
        domain = _mock_domain()
        with patch.object(tc, "del_root_qdisc") as mock_del:
            NetPartitionFault().revert(domain)
        mock_del.assert_called_once_with("vnet0")


class TestNetPartitionErrorPaths:
    def test_inject_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with (
            patch.object(tc, "add_netem_loss"),
            pytest.raises(RuntimeError, match="no network interface"),
        ):
            NetPartitionFault().inject(domain)

    def test_revert_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with (
            patch.object(tc, "del_root_qdisc"),
            pytest.raises(RuntimeError, match="no network interface"),
        ):
            NetPartitionFault().revert(domain)
