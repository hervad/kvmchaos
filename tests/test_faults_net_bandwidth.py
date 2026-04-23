"""Tests for net.bandwidth fault."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import libvirt
import pytest

import kvmchaos.tc as tc
from kvmchaos.faults.net_bandwidth import NetBandwidthFault

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


class TestNetBandwidthMetadata:
    def test_name(self):
        assert NetBandwidthFault.name == "net.bandwidth"

    def test_description_present(self):
        assert NetBandwidthFault.description

    def test_non_destructive(self):
        assert NetBandwidthFault.destructive is False

    def test_local_only(self):
        assert NetBandwidthFault.local_only is True

    def test_default_rate_kbps(self):
        assert NetBandwidthFault().rate_kbps == 1000

    def test_custom_rate_kbps(self):
        assert NetBandwidthFault(rate_kbps=512).rate_kbps == 512


class TestNetBandwidthHappyPath:
    def test_inject_calls_add_netem_rate(self):
        domain = _mock_domain()
        with patch.object(tc, "add_netem_rate") as mock_add:
            NetBandwidthFault().inject(domain)
        mock_add.assert_called_once_with("vnet0", 1000)

    def test_inject_passes_custom_rate(self):
        domain = _mock_domain()
        with patch.object(tc, "add_netem_rate") as mock_add:
            NetBandwidthFault(rate_kbps=256).inject(domain)
        mock_add.assert_called_once_with("vnet0", 256)

    def test_verify_passes_when_netem_rate_present(self):
        domain = _mock_domain()
        with patch.object(
            tc, "show_qdisc", return_value="qdisc netem 8001: root refcnt 2 rate 1000Kbit"
        ):
            NetBandwidthFault().verify(domain)  # must not raise

    def test_verify_raises_when_netem_absent(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "show_qdisc", return_value="qdisc pfifo_fast 0: root"),
            pytest.raises(RuntimeError, match="netem not active"),
        ):
            NetBandwidthFault().verify(domain)

    def test_verify_raises_when_rate_absent(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "show_qdisc", return_value="qdisc netem 8001: root delay 200ms"),
            pytest.raises(RuntimeError, match="bandwidth limit not active"),
        ):
            NetBandwidthFault().verify(domain)

    def test_revert_calls_del_root_qdisc(self):
        domain = _mock_domain()
        with patch.object(tc, "del_root_qdisc") as mock_del:
            NetBandwidthFault().revert(domain)
        mock_del.assert_called_once_with("vnet0")


class TestNetBandwidthErrorPaths:
    def test_inject_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with (
            patch.object(tc, "add_netem_rate"),
            pytest.raises(RuntimeError, match="no network interface"),
        ):
            NetBandwidthFault().inject(domain)

    def test_revert_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with (
            patch.object(tc, "del_root_qdisc"),
            pytest.raises(RuntimeError, match="no network interface"),
        ):
            NetBandwidthFault().revert(domain)

    def test_inject_propagates_tc_error(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "add_netem_rate", side_effect=RuntimeError("tc failed")),
            pytest.raises(RuntimeError, match="tc failed"),
        ):
            NetBandwidthFault().inject(domain)
