"""Tests for net.latency fault.

Mocks at the ``subprocess.run`` boundary rather than at ``tc.add_netem_*``.
This tests the externally-observable effect (the shell command that runs) and
is robust against refactors of the ``tc`` module's internal helper functions.
"""

from unittest.mock import MagicMock, patch

import libvirt
import pytest

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


def _tc_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    """Build a fake subprocess.run CompletedProcess with the given return code and streams."""
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestNetLatencyMetadata:
    def test_name(self):
        assert NetLatencyFault.name == "net.latency"

    def test_description_present(self):
        assert NetLatencyFault.description

    def test_non_destructive(self):
        assert NetLatencyFault.destructive is False


class TestNetLatencyHappyPath:
    def test_inject_runs_tc_netem_delay(self):
        domain = _mock_domain()
        with patch("subprocess.run", return_value=_tc_result()) as mock_run:
            NetLatencyFault().inject(domain)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "replace", "dev", "vnet0", "root", "netem", "delay", "200ms"],
            capture_output=True,
            text=True,
        )

    def test_verify_passes_when_netem_present(self):
        domain = _mock_domain()
        with patch(
            "subprocess.run", return_value=_tc_result(stdout="qdisc netem 8001: root refcnt 2")
        ):
            NetLatencyFault().verify(domain)  # must not raise

    def test_verify_raises_when_netem_absent(self):
        domain = _mock_domain()
        with (
            patch("subprocess.run", return_value=_tc_result(stdout="qdisc fq_codel 0: root")),
            pytest.raises(RuntimeError, match="netem not active"),
        ):
            NetLatencyFault().verify(domain)

    def test_revert_runs_tc_qdisc_del(self):
        domain = _mock_domain()
        with patch("subprocess.run", return_value=_tc_result()) as mock_run:
            NetLatencyFault().revert(domain)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "del", "dev", "vnet0", "root"],
            capture_output=True,
            text=True,
        )


class TestNetLatencyNoInterface:
    def test_inject_raises_when_no_interface(self):
        domain = _mock_domain(xml=_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetLatencyFault().inject(domain)

    def test_verify_raises_when_no_interface(self):
        domain = _mock_domain(xml=_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetLatencyFault().verify(domain)

    def test_revert_raises_when_no_interface(self):
        domain = _mock_domain(xml=_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetLatencyFault().revert(domain)


class TestNetLatencyErrors:
    def test_inject_raises_runtime_error_on_tc_failure(self):
        domain = _mock_domain()
        with (
            patch(
                "subprocess.run",
                return_value=_tc_result(returncode=1, stderr="Operation not permitted"),
            ),
            pytest.raises(RuntimeError, match="Operation not permitted"),
        ):
            NetLatencyFault().inject(domain)

    def test_revert_raises_runtime_error_on_tc_failure(self):
        domain = _mock_domain()
        with (
            patch(
                "subprocess.run",
                return_value=_tc_result(returncode=1, stderr="permission denied"),
            ),
            pytest.raises(RuntimeError, match="permission denied"),
        ):
            NetLatencyFault().revert(domain)
