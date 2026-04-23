"""Tests for disk.latency fault."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import libvirt
import pytest

from kvmchaos.faults.disk_latency import DiskLatencyFault

_XML = """
<domain>
  <devices>
    <disk type='file' device='disk'>
      <source file='/var/lib/libvirt/images/rhel9.7.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
  </devices>
</domain>
"""

_XML_NO_DISK = "<domain><devices></devices></domain>"


def _mock_domain(xml: str = _XML) -> MagicMock:
    domain = MagicMock(spec=libvirt.virDomain)
    domain.name.return_value = "server1"
    domain.XMLDesc.return_value = xml
    return domain


class TestDiskLatencyMetadata:
    def test_name(self):
        assert DiskLatencyFault.name == "disk.latency"

    def test_description_present(self):
        assert DiskLatencyFault.description

    def test_non_destructive(self):
        assert DiskLatencyFault.destructive is False

    def test_local_only(self):
        assert DiskLatencyFault.local_only is True

    def test_default_bandwidth(self):
        fault = DiskLatencyFault()
        assert fault.bandwidth_bps == 1_000_000

    def test_custom_bandwidth(self):
        fault = DiskLatencyFault(bandwidth_bps=2_000_000)
        assert fault.bandwidth_bps == 2_000_000


def _make_stat(major: int, minor: int) -> os.stat_result:
    """Build a fake stat_result with the given device major:minor."""
    fake = MagicMock(spec=os.stat_result)
    fake.st_rdev = os.makedev(major, minor)
    return fake


class TestDiskLatencyInject:
    def test_inject_writes_correct_io_max(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("")
        domain = _mock_domain()
        fault = DiskLatencyFault(bandwidth_bps=1_000_000)

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
        ):
            fault.inject(domain)

        assert io_max.read_text() == "8:0 rbps=1000000 wbps=1000000\n"

    def test_inject_uses_custom_bandwidth(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("")
        domain = _mock_domain()
        fault = DiskLatencyFault(bandwidth_bps=2_000_000)

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
        ):
            fault.inject(domain)

        assert "rbps=2000000 wbps=2000000" in io_max.read_text()


class TestDiskLatencyVerify:
    def test_verify_passes_when_limit_set(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("8:0 rbps=1000000 wbps=1000000\n")
        domain = _mock_domain()
        fault = DiskLatencyFault(bandwidth_bps=1_000_000)

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
        ):
            fault.verify(domain)  # must not raise

    def test_verify_raises_when_limit_absent(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("8:0 rbps=max wbps=max\n")
        domain = _mock_domain()
        fault = DiskLatencyFault(bandwidth_bps=1_000_000)

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
            pytest.raises(RuntimeError, match="not in effect"),
        ):
            fault.verify(domain)

    def test_verify_raises_when_bandwidth_differs(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("8:0 rbps=500000 wbps=500000\n")
        domain = _mock_domain()
        fault = DiskLatencyFault(bandwidth_bps=1_000_000)

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
            pytest.raises(RuntimeError, match="not in effect"),
        ):
            fault.verify(domain)


class TestDiskLatencyRevert:
    def test_revert_writes_max(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("8:0 rbps=1000000 wbps=1000000\n")
        domain = _mock_domain()
        fault = DiskLatencyFault()

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
        ):
            fault.revert(domain)

        assert io_max.read_text() == "8:0 rbps=max wbps=max\n"

    def test_revert_tolerates_missing_cgroup(self):
        domain = _mock_domain()
        fault = DiskLatencyFault()
        with patch(
            "kvmchaos.faults.disk_latency._disk_dev",
            side_effect=FileNotFoundError("no pid file"),
        ):
            fault.revert(domain)  # must not raise

    def test_revert_tolerates_missing_cgroup_hierarchy(self):
        domain = _mock_domain()
        fault = DiskLatencyFault()
        with patch(
            "kvmchaos.faults.disk_latency._disk_dev",
            side_effect=RuntimeError("cgroup not found"),
        ):
            fault.revert(domain)  # must not raise


class TestDiskLatencyHelpers:
    def test_qemu_pid_raises_when_not_running(self):
        from kvmchaos.faults.disk_latency import _qemu_pid

        with patch("kvmchaos.faults.disk_latency.Path") as mock_path:
            mock_path.return_value.read_text.side_effect = FileNotFoundError("no pid file")
            with pytest.raises(FileNotFoundError):
                _qemu_pid("missing-vm")

    def test_disk_dev_parses_xml(self):
        domain = _mock_domain()
        fake_stat = _make_stat(8, 0)
        with (
            patch(
                "kvmchaos.faults.disk_latency._backing_block_device",
                return_value=Path("/dev/sda1"),
            ),
            patch("kvmchaos.faults.disk_latency.os.stat", return_value=fake_stat),
        ):
            from kvmchaos.faults.disk_latency import _disk_dev

            major, minor = _disk_dev(domain)
        assert major == 8
        assert minor == 0

    def test_disk_dev_raises_when_no_disk(self):
        domain = _mock_domain(_XML_NO_DISK)
        from kvmchaos.faults.disk_latency import _disk_dev

        with pytest.raises(RuntimeError, match="No disk source"):
            _disk_dev(domain)

    def test_io_max_path_raises_when_no_cgroup_v2(self):
        from kvmchaos.faults.disk_latency import _io_max_path

        # cgroup v1 format has no "0::" line
        cgroup_v1 = "1:cpu:/system.slice\n2:memory:/system.slice\n"
        with (
            patch("kvmchaos.faults.disk_latency._qemu_pid", return_value=12345),
            patch.object(Path, "read_text", return_value=cgroup_v1),
            pytest.raises(RuntimeError, match="cgroups v2 hierarchy not found"),
        ):
            _io_max_path("server1")


class TestFindIoCgroup:
    def test_returns_start_when_it_has_io(self, tmp_path: Path):
        from kvmchaos.faults.disk_latency import _find_io_cgroup

        (tmp_path / "cgroup.controllers").write_text("cpuset cpu io memory pids\n")
        assert _find_io_cgroup(tmp_path) == tmp_path

    def test_walks_up_to_nearest_ancestor(self, tmp_path: Path):
        from kvmchaos.faults.disk_latency import _find_io_cgroup

        scope = tmp_path / "scope"
        libvirt_dir = scope / "libvirt"
        emulator = libvirt_dir / "emulator"
        emulator.mkdir(parents=True)
        (scope / "cgroup.controllers").write_text("cpuset cpu io memory pids\n")
        (libvirt_dir / "cgroup.controllers").write_text("cpuset cpu io memory\n")
        (emulator / "cgroup.controllers").write_text("cpuset cpu\n")

        assert _find_io_cgroup(emulator) == libvirt_dir

    def test_raises_when_no_ancestor_has_io(self, tmp_path: Path):
        from kvmchaos.faults.disk_latency import _find_io_cgroup

        leaf = tmp_path / "leaf"
        leaf.mkdir()
        (tmp_path / "cgroup.controllers").write_text("cpuset cpu\n")
        (leaf / "cgroup.controllers").write_text("cpuset cpu\n")

        with pytest.raises(RuntimeError, match="no ancestor"):
            _find_io_cgroup(leaf)


class TestBackingBlockDevice:
    def test_picks_longest_matching_mount(self, tmp_path: Path):
        from kvmchaos.faults.disk_latency import _backing_block_device

        mountinfo = (
            "1 0 0:1 / / rw - rootfs rootfs rw\n"
            "2 1 259:9 / /var/lib/libvirt rw - btrfs /dev/nvme0n1p6 rw\n"
            "3 1 0:36 / /tmp rw - tmpfs tmpfs rw\n"
        )
        target = tmp_path / "var" / "lib" / "libvirt" / "images" / "vm.qcow2"
        target.parent.mkdir(parents=True)
        target.write_text("")

        def fake_read_text(self, *a, **kw):
            if str(self) == "/proc/self/mountinfo":
                return mountinfo
            return ""

        # Resolve target under a fake mount prefix to force the match.
        with (
            patch.object(Path, "read_text", autospec=True, side_effect=fake_read_text),
            patch.object(Path, "resolve", return_value=Path("/var/lib/libvirt/images/vm.qcow2")),
        ):
            result = _backing_block_device(target)
        assert str(result) == "/dev/nvme0n1p6"

    def test_raises_for_non_block_source(self, tmp_path: Path):
        from kvmchaos.faults.disk_latency import _backing_block_device

        mountinfo = "1 0 0:1 / /tmp rw - tmpfs tmpfs rw\n"
        target = tmp_path / "tmp" / "x"
        target.parent.mkdir(parents=True)
        target.write_text("")

        def fake_read_text(self, *a, **kw):
            if str(self) == "/proc/self/mountinfo":
                return mountinfo
            return ""

        with (
            patch.object(Path, "read_text", autospec=True, side_effect=fake_read_text),
            patch.object(Path, "resolve", return_value=Path("/tmp/x")),
            pytest.raises(RuntimeError, match="cannot resolve"),
        ):
            _backing_block_device(target)


class TestWholeDisk:
    def test_partition_resolves_to_whole_disk(self, tmp_path: Path):
        from kvmchaos.faults.disk_latency import _whole_disk

        # Simulate /sys layout: realpath("/sys/dev/block/8:1") -> <tmp>/sda/sda1
        # parent <tmp>/sda contains dev file with "8:0"
        sda = tmp_path / "sda"
        sda.mkdir()
        (sda / "dev").write_text("8:0\n")
        sda1 = sda / "sda1"
        sda1.mkdir()
        (sda1 / "dev").write_text("8:1\n")

        with patch("kvmchaos.faults.disk_latency.os.path.realpath", return_value=str(sda1)):
            major, minor = _whole_disk(8, 1)
        assert (major, minor) == (8, 0)

    def test_whole_disk_returns_unchanged(self, tmp_path: Path):
        from kvmchaos.faults.disk_latency import _whole_disk

        sda = tmp_path / "sda"
        sda.mkdir()
        (sda / "dev").write_text("8:0\n")
        # Parent of sda (tmp_path) has no dev file → already whole disk.

        with patch("kvmchaos.faults.disk_latency.os.path.realpath", return_value=str(sda)):
            major, minor = _whole_disk(8, 0)
        assert (major, minor) == (8, 0)

    def test_whole_disk_missing_sys_returns_unchanged(self):
        from kvmchaos.faults.disk_latency import _whole_disk

        with patch(
            "kvmchaos.faults.disk_latency.os.path.realpath",
            return_value="/nonexistent/path",
        ):
            major, minor = _whole_disk(253, 0)
        assert (major, minor) == (253, 0)
