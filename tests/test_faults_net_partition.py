"""Tests for net.partition fault."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import libvirt
import pytest

import kvmchaos.nft as nft
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
    def test_inject_calls_add_partition(self):
        domain = _mock_domain()
        with patch.object(nft, "add_partition") as mock_add:
            NetPartitionFault().inject(domain)
        mock_add.assert_called_once_with("vnet0")

    def test_verify_passes_when_table_exists(self):
        domain = _mock_domain()
        with patch.object(nft, "partition_active", return_value=True):
            NetPartitionFault().verify(domain)  # must not raise

    def test_verify_raises_when_table_absent(self):
        domain = _mock_domain()
        with (
            patch.object(nft, "partition_active", return_value=False),
            pytest.raises(RuntimeError, match=r"net\.partition not in effect"),
        ):
            NetPartitionFault().verify(domain)

    def test_revert_calls_del_partition(self):
        domain = _mock_domain()
        with patch.object(nft, "del_partition") as mock_del:
            NetPartitionFault().revert(domain)
        mock_del.assert_called_once_with("vnet0")


class TestNetPartitionErrorPaths:
    def test_inject_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with (
            patch.object(nft, "add_partition"),
            pytest.raises(RuntimeError, match="no network interface"),
        ):
            NetPartitionFault().inject(domain)

    def test_revert_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with (
            patch.object(nft, "del_partition"),
            pytest.raises(RuntimeError, match="no network interface"),
        ):
            NetPartitionFault().revert(domain)


class TestNftModule:
    def test_add_partition_creates_table_and_rules(self):
        with patch("kvmchaos.nft.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            nft.add_partition("vnet0")
        # Single _run_script call via nft -f -
        mock_run.assert_called_once()
        script = mock_run.call_args.kwargs["input"]
        assert "iifname" in script and "drop" in script
        assert "oifname" in script and "drop" in script
        assert "hook forward" in script

    def test_del_partition_deletes_table(self):
        with patch("kvmchaos.nft.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            nft.del_partition("vnet0")
        cmd = mock_run.call_args[0][0]
        assert "delete" in cmd
        assert "table" in cmd

    def test_partition_active_returns_true_when_table_exists(self):
        with patch("kvmchaos.nft.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="table inet kvmchaos-vnet0")
            result = nft.partition_active("vnet0")
        assert result is True

    def test_partition_active_returns_false_when_table_absent(self):
        with patch("kvmchaos.nft.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = nft.partition_active("vnet0")
        assert result is False

    def test_add_partition_raises_on_nft_failure(self):
        with patch("kvmchaos.nft.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Operation not permitted")
            with pytest.raises(RuntimeError, match="nft script failed"):
                nft.add_partition("vnet0")
