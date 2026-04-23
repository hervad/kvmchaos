"""Tests for net.partition fault.

Mocks at the ``subprocess.run`` boundary rather than at ``tc.add_netem_*``.
This tests the externally-observable effect (the shell command that runs) and
is robust against refactors of the ``tc`` module's internal helper functions.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import libvirt
import pytest

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


def _tc_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


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
    def test_inject_runs_tc_netem_loss_100_percent(self):
        domain = _mock_domain()
        with patch("subprocess.run", return_value=_tc_result()) as mock_run:
            NetPartitionFault().inject(domain)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "replace", "dev", "vnet0", "root", "netem", "loss", "100%"],
            capture_output=True,
            text=True,
        )

    def test_verify_passes_when_netem_loss_present(self):
        domain = _mock_domain()
        with patch(
            "subprocess.run",
            return_value=_tc_result(stdout="qdisc netem 8001: root refcnt 2 loss 100%"),
        ):
            NetPartitionFault().verify(domain)  # must not raise

    def test_verify_raises_when_netem_absent(self):
        domain = _mock_domain()
        with (
            patch("subprocess.run", return_value=_tc_result(stdout="qdisc pfifo_fast 0: root")),
            pytest.raises(RuntimeError, match=r"netem not active"),
        ):
            NetPartitionFault().verify(domain)

    def test_verify_raises_when_loss_absent(self):
        domain = _mock_domain()
        with (
            patch(
                "subprocess.run",
                return_value=_tc_result(stdout="qdisc netem 8001: root delay 200ms"),
            ),
            pytest.raises(RuntimeError, match=r"packet loss not active"),
        ):
            NetPartitionFault().verify(domain)

    def test_revert_runs_tc_qdisc_del(self):
        domain = _mock_domain()
        with patch("subprocess.run", return_value=_tc_result()) as mock_run:
            NetPartitionFault().revert(domain)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "del", "dev", "vnet0", "root"],
            capture_output=True,
            text=True,
        )


class TestNetPartitionErrorPaths:
    def test_inject_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetPartitionFault().inject(domain)

    def test_revert_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetPartitionFault().revert(domain)

    def test_inject_raises_runtime_error_on_tc_failure(self):
        domain = _mock_domain()
        with (
            patch(
                "subprocess.run",
                return_value=_tc_result(returncode=1, stderr="Operation not permitted"),
            ),
            pytest.raises(RuntimeError, match="Operation not permitted"),
        ):
            NetPartitionFault().inject(domain)
