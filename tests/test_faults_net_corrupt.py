"""Tests for net.corrupt fault."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import libvirt
import pytest

import kvmchaos.tc as tc
from kvmchaos.faults.net_corrupt import NetCorruptFault

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


class TestNetCorruptMetadata:
    def test_name(self):
        assert NetCorruptFault.name == "net.corrupt"

    def test_description_present(self):
        assert NetCorruptFault.description

    def test_non_destructive(self):
        assert NetCorruptFault.destructive is False

    def test_local_only(self):
        assert NetCorruptFault.local_only is True

    def test_default_corrupt_percent(self):
        assert NetCorruptFault().corrupt_percent == 1

    def test_custom_corrupt_percent(self):
        assert NetCorruptFault(corrupt_percent=5).corrupt_percent == 5


class TestNetCorruptHappyPath:
    def test_inject_calls_add_netem_corrupt(self):
        domain = _mock_domain()
        with patch.object(tc, "add_netem_corrupt") as mock_add:
            NetCorruptFault().inject(domain)
        mock_add.assert_called_once_with("vnet0", 1)

    def test_inject_passes_custom_percent(self):
        domain = _mock_domain()
        with patch.object(tc, "add_netem_corrupt") as mock_add:
            NetCorruptFault(corrupt_percent=5).inject(domain)
        mock_add.assert_called_once_with("vnet0", 5)

    def test_verify_passes_when_netem_corrupt_present(self):
        domain = _mock_domain()
        with patch.object(
            tc, "show_qdisc", return_value="qdisc netem 8001: root refcnt 2 corrupt 1%"
        ):
            NetCorruptFault().verify(domain)  # must not raise

    def test_verify_raises_when_netem_absent(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "show_qdisc", return_value="qdisc pfifo_fast 0: root"),
            pytest.raises(RuntimeError, match="netem not active"),
        ):
            NetCorruptFault().verify(domain)

    def test_verify_raises_when_corrupt_absent(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "show_qdisc", return_value="qdisc netem 8001: root delay 200ms"),
            pytest.raises(RuntimeError, match="corruption not active"),
        ):
            NetCorruptFault().verify(domain)

    def test_revert_calls_del_root_qdisc(self):
        domain = _mock_domain()
        with patch.object(tc, "del_root_qdisc") as mock_del:
            NetCorruptFault().revert(domain)
        mock_del.assert_called_once_with("vnet0")


class TestNetCorruptErrorPaths:
    def test_inject_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetCorruptFault().inject(domain)

    def test_revert_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with pytest.raises(RuntimeError, match="no network interface"):
            NetCorruptFault().revert(domain)

    def test_inject_propagates_tc_error(self):
        domain = _mock_domain()
        with (
            patch.object(
                tc, "add_netem_corrupt", side_effect=RuntimeError("Operation not permitted")
            ),
            pytest.raises(RuntimeError, match="Operation not permitted"),
        ):
            NetCorruptFault().inject(domain)
