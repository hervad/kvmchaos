"""Tests for net.packet-loss fault."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import libvirt
import pytest

import kvmchaos.tc as tc
from kvmchaos.faults.net_packet_loss import NetPacketLossFault

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


class TestNetPacketLossMetadata:
    def test_name(self):
        assert NetPacketLossFault.name == "net.packet-loss"

    def test_description_present(self):
        assert NetPacketLossFault.description

    def test_non_destructive(self):
        assert NetPacketLossFault.destructive is False

    def test_local_only(self):
        assert NetPacketLossFault.local_only is True

    def test_default_loss_percent(self):
        assert NetPacketLossFault().loss_percent == 50

    def test_custom_loss_percent(self):
        assert NetPacketLossFault(loss_percent=10).loss_percent == 10


class TestNetPacketLossHappyPath:
    def test_inject_calls_add_netem_loss(self):
        domain = _mock_domain()
        with patch.object(tc, "add_netem_loss") as mock_add:
            NetPacketLossFault().inject(domain)
        mock_add.assert_called_once_with("vnet0", 50)

    def test_inject_passes_custom_loss(self):
        domain = _mock_domain()
        with patch.object(tc, "add_netem_loss") as mock_add:
            NetPacketLossFault(loss_percent=25).inject(domain)
        mock_add.assert_called_once_with("vnet0", 25)

    def test_verify_passes_when_netem_loss_present(self):
        domain = _mock_domain()
        with patch.object(
            tc, "show_qdisc", return_value="qdisc netem 8001: root refcnt 2 loss 50%"
        ):
            NetPacketLossFault().verify(domain)  # must not raise

    def test_verify_raises_when_netem_absent(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "show_qdisc", return_value="qdisc pfifo_fast 0: root"),
            pytest.raises(RuntimeError, match="netem not active"),
        ):
            NetPacketLossFault().verify(domain)

    def test_verify_raises_when_loss_absent(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "show_qdisc", return_value="qdisc netem 8001: root delay 200ms"),
            pytest.raises(RuntimeError, match="packet loss not active"),
        ):
            NetPacketLossFault().verify(domain)

    def test_revert_calls_del_root_qdisc(self):
        domain = _mock_domain()
        with patch.object(tc, "del_root_qdisc") as mock_del:
            NetPacketLossFault().revert(domain)
        mock_del.assert_called_once_with("vnet0")


class TestNetPacketLossErrorPaths:
    def test_inject_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with (
            patch.object(tc, "add_netem_loss"),
            pytest.raises(RuntimeError, match="no network interface"),
        ):
            NetPacketLossFault().inject(domain)

    def test_revert_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with (
            patch.object(tc, "del_root_qdisc"),
            pytest.raises(RuntimeError, match="no network interface"),
        ):
            NetPacketLossFault().revert(domain)


class TestTcAddNetemLoss:
    def test_calls_tc_with_correct_args(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            tc.add_netem_loss("vnet0", 30)
        cmd = mock_run.call_args[0][0]
        assert cmd == ["tc", "qdisc", "replace", "dev", "vnet0", "root", "netem", "loss", "30%"]

    def test_raises_on_tc_failure(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="RTNETLINK answers: No such file"
            )
            with pytest.raises(RuntimeError, match="tc command failed"):
                tc.add_netem_loss("vnet99", 50)
