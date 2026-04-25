"""Tests for net.bandwidth fault.

Mocks at the ``subprocess.run`` boundary rather than at ``tc.add_netem_*``.
This tests the externally-observable effect (the shell command that runs) and
is robust against refactors of the ``tc`` module's internal helper functions.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import libvirt
import pytest

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


def _tc_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestNetBandwidthMetadata:
    def test_name(self):
        assert NetBandwidthFault.name == "net.bandwidth"

    def test_description_present(self):
        assert NetBandwidthFault.description

    def test_non_destructive(self):
        assert NetBandwidthFault.destructive is False

    def test_default_rate_kbps(self):
        assert NetBandwidthFault().rate_kbps == 1000

    def test_custom_rate_kbps(self):
        assert NetBandwidthFault(rate_kbps=512).rate_kbps == 512


class TestNetBandwidthHappyPath:
    def test_inject_runs_tc_netem_rate(self):
        domain = _mock_domain()
        with patch("subprocess.run", return_value=_tc_result()) as mock_run:
            NetBandwidthFault().inject(domain)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "replace", "dev", "vnet0", "root", "netem", "rate", "1000kbit"],
            capture_output=True,
            text=True,
        )

    def test_inject_passes_custom_rate(self):
        domain = _mock_domain()
        with patch("subprocess.run", return_value=_tc_result()) as mock_run:
            NetBandwidthFault(rate_kbps=256).inject(domain)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "replace", "dev", "vnet0", "root", "netem", "rate", "256kbit"],
            capture_output=True,
            text=True,
        )

    def test_verify_passes_when_netem_rate_present(self):
        domain = _mock_domain()
        with patch(
            "subprocess.run",
            return_value=_tc_result(stdout="qdisc netem 8001: root refcnt 2 rate 1000Kbit"),
        ):
            NetBandwidthFault().verify(domain)  # must not raise

    def test_verify_raises_when_netem_absent(self):
        domain = _mock_domain()
        with (
            patch("subprocess.run", return_value=_tc_result(stdout="qdisc pfifo_fast 0: root")),
            pytest.raises(RuntimeError, match="netem not active"),
        ):
            NetBandwidthFault().verify(domain)

    def test_verify_raises_when_rate_absent(self):
        domain = _mock_domain()
        with (
            patch(
                "subprocess.run",
                return_value=_tc_result(stdout="qdisc netem 8001: root delay 200ms"),
            ),
            pytest.raises(RuntimeError, match="bandwidth limit not active"),
        ):
            NetBandwidthFault().verify(domain)

    def test_revert_runs_tc_qdisc_del(self):
        domain = _mock_domain()
        with patch("subprocess.run", return_value=_tc_result()) as mock_run:
            NetBandwidthFault().revert(domain)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "del", "dev", "vnet0", "root"],
            capture_output=True,
            text=True,
        )


class TestNetBandwidthErrorPaths:
    def test_inject_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetBandwidthFault().inject(domain)

    def test_revert_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetBandwidthFault().revert(domain)

    def test_inject_raises_runtime_error_on_tc_failure(self):
        domain = _mock_domain()
        with (
            patch(
                "subprocess.run",
                return_value=_tc_result(returncode=1, stderr="Operation not permitted"),
            ),
            pytest.raises(RuntimeError, match="Operation not permitted"),
        ):
            NetBandwidthFault().inject(domain)
