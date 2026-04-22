"""Tests for net.latency fault."""

from unittest.mock import MagicMock, patch

import libvirt
import pytest

import kvmchaos.tc as tc
from kvmchaos.faults.net_latency import NetLatencyFault

_XML_ONE_IFACE = """
<domain>
  <devices>
    <interface type='network'>
      <target dev='vnet0'/>
    </interface>
  </devices>
</domain>
"""

_XML_NO_IFACE = "<domain><devices></devices></domain>"


def _mock_domain(xml: str = _XML_ONE_IFACE) -> MagicMock:
    domain = MagicMock(spec=libvirt.virDomain)
    domain.name.return_value = "testvm"
    domain.XMLDesc.return_value = xml
    return domain


class TestNetLatencyMetadata:
    def test_name(self):
        assert NetLatencyFault.name == "net.latency"

    def test_description_present(self):
        assert NetLatencyFault.description

    def test_non_destructive(self):
        assert NetLatencyFault.destructive is False


class TestNetLatencyHappyPath:
    def test_inject_calls_add_netem_delay(self):
        domain = _mock_domain()
        with patch.object(tc, "add_netem_delay") as mock_add:
            NetLatencyFault().inject(domain)
            mock_add.assert_called_once_with("vnet0", 200)

    def test_verify_passes_when_netem_present(self):
        domain = _mock_domain()
        with patch.object(tc, "show_qdisc", return_value="qdisc netem 8001: root refcnt 2"):
            NetLatencyFault().verify(domain)  # must not raise

    def test_verify_raises_when_netem_absent(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "show_qdisc", return_value="qdisc fq_codel 0: root"),
            pytest.raises(RuntimeError, match="netem not active"),
        ):
            NetLatencyFault().verify(domain)

    def test_revert_calls_del_root_qdisc(self):
        domain = _mock_domain()
        with patch.object(tc, "del_root_qdisc") as mock_del:
            NetLatencyFault().revert(domain)
            mock_del.assert_called_once_with("vnet0")


class TestNetLatencyNoInterface:
    def test_inject_raises_when_no_interface(self):
        domain = _mock_domain(xml=_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetLatencyFault().inject(domain)

    def test_revert_raises_when_no_interface(self):
        domain = _mock_domain(xml=_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetLatencyFault().revert(domain)


class TestNetLatencyErrors:
    def test_inject_propagates_tc_error(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "add_netem_delay", side_effect=RuntimeError("tc failed")),
            pytest.raises(RuntimeError, match="tc failed"),
        ):
            NetLatencyFault().inject(domain)

    def test_revert_propagates_tc_error(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "del_root_qdisc", side_effect=RuntimeError("tc failed")),
            pytest.raises(RuntimeError, match="tc failed"),
        ):
            NetLatencyFault().revert(domain)
