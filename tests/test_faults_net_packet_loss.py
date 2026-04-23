"""Tests for net.packet-loss fault.

Mocks at the ``subprocess.run`` boundary rather than at ``tc.add_netem_*``.
This tests the externally-observable effect (the shell command that runs) and
is robust against refactors of the ``tc`` module's internal helper functions.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import libvirt
import pytest

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


def _tc_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


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
        assert NetPacketLossFault().loss_percent == 10

    def test_custom_loss_percent(self):
        assert NetPacketLossFault(loss_percent=25).loss_percent == 25


class TestNetPacketLossHappyPath:
    def test_inject_runs_tc_netem_loss(self):
        domain = _mock_domain()
        with patch("subprocess.run", return_value=_tc_result()) as mock_run:
            NetPacketLossFault().inject(domain)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "replace", "dev", "vnet0", "root", "netem", "loss", "10%"],
            capture_output=True,
            text=True,
        )

    def test_inject_passes_custom_loss(self):
        domain = _mock_domain()
        with patch("subprocess.run", return_value=_tc_result()) as mock_run:
            NetPacketLossFault(loss_percent=25).inject(domain)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "replace", "dev", "vnet0", "root", "netem", "loss", "25%"],
            capture_output=True,
            text=True,
        )

    def test_verify_passes_when_netem_loss_present(self):
        domain = _mock_domain()
        with patch(
            "subprocess.run",
            return_value=_tc_result(stdout="qdisc netem 8001: root refcnt 2 loss 50%"),
        ):
            NetPacketLossFault().verify(domain)  # must not raise

    def test_verify_raises_when_netem_absent(self):
        domain = _mock_domain()
        with (
            patch("subprocess.run", return_value=_tc_result(stdout="qdisc pfifo_fast 0: root")),
            pytest.raises(RuntimeError, match="netem not active"),
        ):
            NetPacketLossFault().verify(domain)

    def test_verify_raises_when_loss_absent(self):
        domain = _mock_domain()
        with (
            patch(
                "subprocess.run",
                return_value=_tc_result(stdout="qdisc netem 8001: root delay 200ms"),
            ),
            pytest.raises(RuntimeError, match="packet loss not active"),
        ):
            NetPacketLossFault().verify(domain)

    def test_revert_runs_tc_qdisc_del(self):
        domain = _mock_domain()
        with patch("subprocess.run", return_value=_tc_result()) as mock_run:
            NetPacketLossFault().revert(domain)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "del", "dev", "vnet0", "root"],
            capture_output=True,
            text=True,
        )


class TestNetPacketLossErrorPaths:
    def test_inject_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetPacketLossFault().inject(domain)

    def test_revert_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetPacketLossFault().revert(domain)

    def test_inject_raises_runtime_error_on_tc_failure(self):
        domain = _mock_domain()
        with (
            patch(
                "subprocess.run",
                return_value=_tc_result(returncode=1, stderr="Operation not permitted"),
            ),
            pytest.raises(RuntimeError, match="Operation not permitted"),
        ):
            NetPacketLossFault().inject(domain)
