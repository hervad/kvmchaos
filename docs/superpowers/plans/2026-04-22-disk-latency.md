# disk.latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `disk.latency` fault that throttles a VM's disk I/O to a configurable MB/s limit via Linux cgroup v2 `io.max`, simulating slow storage.

**Architecture:** `DiskLatencyFault` reads the QEMU PID from `/var/run/libvirt/qemu/<vm>.pid`, resolves the cgroup path via `/proc/<pid>/cgroup`, determines the disk's major:minor numbers from the domain XML + `os.stat`, and writes to `<cgroup>/io.max`. Unlike other faults it is stateful (stores `bandwidth_bps`) and instantiated fresh per CLI invocation. The CLI adds a `--bandwidth` flag; `FAULTS` stores a default sentinel instance.

**Tech Stack:** Python 3.14, libvirt-python, typer, xml.etree.ElementTree, os, pathlib — no new dependencies.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `src/kvmchaos/faults/disk_latency.py` | Create | `DiskLatencyFault` class |
| `src/kvmchaos/faults/__init__.py` | Modify | Import + register `DiskLatencyFault` |
| `src/kvmchaos/cli.py` | Modify | Add `--bandwidth` flag, instantiate per-run |
| `tests/test_disk_latency.py` | Create | Unit tests for the fault |
| `tests/test_fault_local_only.py` | Modify | Assert `disk.latency` is `local_only` |
| `tests/test_cli.py` | Modify | Assert `--bandwidth` flag is wired up |

---

## Task 1: `DiskLatencyFault` class

**Files:**
- Create: `src/kvmchaos/faults/disk_latency.py`
- Create: `tests/test_disk_latency.py`

- [ ] **Step 1.1: Write the failing metadata tests**

Create `tests/test_disk_latency.py`:

```python
"""Tests for disk.latency fault."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

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
```

- [ ] **Step 1.2: Run to confirm failure**

```bash
uv run pytest tests/test_disk_latency.py::TestDiskLatencyMetadata -v
```

Expected: `ModuleNotFoundError: No module named 'kvmchaos.faults.disk_latency'`

- [ ] **Step 1.3: Create `src/kvmchaos/faults/disk_latency.py` with metadata only**

```python
"""`disk.latency` fault — throttle VM disk I/O via cgroup v2 io.max.

Writes a bandwidth limit to the QEMU process's blkio cgroup, causing all
disk I/O from the VM to be throttled to ``bandwidth_bps`` bytes per second.

Requires root (cgroup writes are privileged). The VM disk must be a file-backed
device (qcow2 or raw) on a local filesystem.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import ClassVar

import libvirt


class DiskLatencyFault:
    """Throttle VM disk I/O to simulate slow storage via cgroup v2 io.max.

    Implements the ``Fault`` protocol. Unlike other faults, this class is
    stateful: ``bandwidth_bps`` is set at construction time and used across
    inject/verify/revert.
    """

    name: ClassVar[str] = "disk.latency"
    description: ClassVar[str] = "Throttle VM disk I/O to N MB/s via cgroup v2 io.max."
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def __init__(self, bandwidth_bps: int = 1_000_000) -> None:
        """Initialise with a bandwidth limit.

        Args:
            bandwidth_bps: Throttle limit in bytes per second. Default 1 MB/s.
        """
        self.bandwidth_bps = bandwidth_bps

    def inject(self, domain: libvirt.virDomain) -> None:
        """Throttle the domain's disk I/O via cgroup io.max.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            FileNotFoundError: If the QEMU PID file is not found (VM not running).
            RuntimeError: If the cgroup path or disk device cannot be resolved.
            PermissionError: If writing to the cgroup requires elevated privileges.
        """
        major, minor = _disk_dev(domain)
        io_max = _io_max_path(domain.name())
        io_max.write_text(
            f"{major}:{minor} rbps={self.bandwidth_bps} wbps={self.bandwidth_bps}\n"
        )

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that the io.max throttle is in effect.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If the throttle entry is absent or has wrong values.
        """
        major, minor = _disk_dev(domain)
        io_max = _io_max_path(domain.name())
        content = io_max.read_text()
        expected = f"{major}:{minor} rbps={self.bandwidth_bps} wbps={self.bandwidth_bps}"
        if expected not in content:
            raise RuntimeError(
                f"disk.latency not in effect for {domain.name()}: expected {expected!r} in io.max"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Remove the io.max throttle, restoring full disk I/O speed.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If the cgroup path cannot be resolved.
        """
        major, minor = _disk_dev(domain)
        io_max = _io_max_path(domain.name())
        io_max.write_text(f"{major}:{minor} rbps=max wbps=max\n")


def _qemu_pid(vm_name: str) -> int:
    """Read the QEMU PID from libvirt's pid file for the named domain.

    Args:
        vm_name: libvirt domain name.

    Returns:
        Integer PID of the running QEMU process.

    Raises:
        FileNotFoundError: If the PID file does not exist (VM not running).
    """
    return int(Path(f"/var/run/libvirt/qemu/{vm_name}.pid").read_text().strip())


def _io_max_path(vm_name: str) -> Path:
    """Resolve the absolute path to the cgroup io.max file for a QEMU process.

    Reads ``/proc/<pid>/cgroup`` to find the cgroups v2 path, then constructs
    the absolute path under ``/sys/fs/cgroup``.

    Args:
        vm_name: libvirt domain name.

    Returns:
        Absolute ``Path`` to the ``io.max`` file.

    Raises:
        FileNotFoundError: If the PID file does not exist.
        RuntimeError: If no cgroups v2 entry is found in the process cgroup file.
    """
    pid = _qemu_pid(vm_name)
    for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
        if line.startswith("0::"):
            rel = line[3:].lstrip("/")
            return Path("/sys/fs/cgroup") / rel / "io.max"
    raise RuntimeError(f"cgroups v2 hierarchy not found in /proc/{pid}/cgroup")


def _disk_dev(domain: libvirt.virDomain) -> tuple[int, int]:
    """Return (major, minor) of the filesystem device holding the VM's first disk.

    Parses the domain XML to find the first ``<disk device='disk'>`` source file,
    then calls ``os.stat`` to get the device numbers of the filesystem it lives on.

    Args:
        domain: A live libvirt domain handle.

    Returns:
        Tuple of (major, minor) integers for use in cgroup io.max entries.

    Raises:
        RuntimeError: If no disk source file is found in the domain XML.
    """
    root = ET.fromstring(domain.XMLDesc())
    elem = root.find(".//disk[@device='disk']/source")
    if elem is None:
        raise RuntimeError(f"No disk source found in domain XML for {domain.name()}")
    source_file = elem.get("file")
    if not source_file:
        raise RuntimeError(f"Disk source has no file attribute for {domain.name()}")
    st = os.stat(source_file)
    return os.major(st.st_dev), os.minor(st.st_dev)
```

- [ ] **Step 1.4: Run metadata tests**

```bash
uv run pytest tests/test_disk_latency.py::TestDiskLatencyMetadata -v
```

Expected: `6 passed`

- [ ] **Step 1.5: Write inject/verify/revert tests**

Append to `tests/test_disk_latency.py`:

```python
def _make_stat(major: int, minor: int) -> os.stat_result:
    """Build a fake stat_result with the given device major:minor."""
    fake = MagicMock(spec=os.stat_result)
    fake.st_dev = os.makedev(major, minor)
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
        ):
            with pytest.raises(RuntimeError, match="not in effect"):
                fault.verify(domain)

    def test_verify_raises_when_bandwidth_differs(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("8:0 rbps=500000 wbps=500000\n")
        domain = _mock_domain()
        fault = DiskLatencyFault(bandwidth_bps=1_000_000)

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
        ):
            with pytest.raises(RuntimeError):
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


class TestDiskLatencyHelpers:
    def test_qemu_pid_raises_when_not_running(self, tmp_path: Path):
        with patch(
            "kvmchaos.faults.disk_latency.Path",
            side_effect=FileNotFoundError("no pid file"),
        ):
            from kvmchaos.faults.disk_latency import _qemu_pid
            with pytest.raises(FileNotFoundError):
                _qemu_pid("missing-vm")

    def test_disk_dev_parses_xml(self):
        domain = _mock_domain()
        fake_stat = _make_stat(8, 0)
        with patch("kvmchaos.faults.disk_latency.os.stat", return_value=fake_stat):
            from kvmchaos.faults.disk_latency import _disk_dev
            major, minor = _disk_dev(domain)
        assert major == 8
        assert minor == 0

    def test_disk_dev_raises_when_no_disk(self):
        domain = _mock_domain(_XML_NO_DISK)
        from kvmchaos.faults.disk_latency import _disk_dev
        with pytest.raises(RuntimeError, match="No disk source"):
            _disk_dev(domain)
```

- [ ] **Step 1.6: Run all disk_latency tests**

```bash
uv run pytest tests/test_disk_latency.py -v
```

Expected: all tests pass

- [ ] **Step 1.7: Commit**

```bash
git add src/kvmchaos/faults/disk_latency.py tests/test_disk_latency.py
git commit -m "feat: add DiskLatencyFault class with cgroup v2 io.max throttle"
```

---

## Task 2: Registry, CLI `--bandwidth` flag, and integration tests

**Files:**
- Modify: `src/kvmchaos/faults/__init__.py`
- Modify: `src/kvmchaos/cli.py`
- Modify: `tests/test_fault_local_only.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 2.1: Write failing local_only test**

In `tests/test_fault_local_only.py`, add to the existing `TestLocalOnlyAttribute` class:

```python
def test_disk_latency_is_local_only(self):
    from kvmchaos.faults import FAULTS
    assert FAULTS["disk.latency"].local_only is True
```

Run:
```bash
uv run pytest tests/test_fault_local_only.py::TestLocalOnlyAttribute::test_disk_latency_is_local_only -v
```

Expected: `KeyError: 'disk.latency'`

- [ ] **Step 2.2: Register `DiskLatencyFault` in `FAULTS`**

In `src/kvmchaos/faults/__init__.py`, add the import and entry:

```python
"""Fault registry.

Maps fault name strings to singleton `Fault` instances.
Adding a fault requires: writing the class, importing it here,
and adding one entry to `FAULTS`. No decorators or entry-point magic.
"""

from __future__ import annotations

from kvmchaos.faults.base import Fault
from kvmchaos.faults.disk_latency import DiskLatencyFault
from kvmchaos.faults.net_latency import NetLatencyFault
from kvmchaos.faults.vm_freeze import VmFreezeFault
from kvmchaos.faults.vm_kill import VmKillFault
from kvmchaos.faults.vm_pause import VmPauseFault
from kvmchaos.faults.vm_starve import VmStarveFault

FAULTS: dict[str, Fault] = {
    VmPauseFault.name: VmPauseFault(),
    VmKillFault.name: VmKillFault(),
    VmFreezeFault.name: VmFreezeFault(),
    VmStarveFault.name: VmStarveFault(),
    NetLatencyFault.name: NetLatencyFault(),
    DiskLatencyFault.name: DiskLatencyFault(),
}
```

- [ ] **Step 2.3: Run local_only test**

```bash
uv run pytest tests/test_fault_local_only.py -v
```

Expected: all pass (including new `test_disk_latency_is_local_only`)

- [ ] **Step 2.4: Write failing CLI --bandwidth test**

In `tests/test_cli.py`, add to the `TestListFaults` class (or a new class at the end):

```python
class TestBandwidthFlag:
    def test_disk_latency_appears_in_list_faults(self):
        result = runner.invoke(app, ["list-faults"])
        assert result.exit_code == 0
        assert "disk.latency" in result.stdout

    def test_bandwidth_flag_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from unittest.mock import MagicMock, patch
        from kvmchaos.faults.disk_latency import DiskLatencyFault

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        captured: list[DiskLatencyFault] = []

        original_run_step = __import__("kvmchaos.cli", fromlist=["_run_step"])._run_step

        def capturing_run_step(func, domain, *, action, fault_name, vm, dry_run=False):
            return {"action": action, "result": "skipped", "duration_ms": 0}

        with patch("kvmchaos.cli._run_step", side_effect=capturing_run_step):
            with patch("kvmchaos.cli.FAULTS", {
                "disk.latency": DiskLatencyFault(),
            }):
                with patch("kvmchaos.cli.connect") as mock_conn:
                    mock_domain = MagicMock()
                    mock_conn.return_value.__enter__.return_value.lookupByName.return_value = mock_domain
                    result = runner.invoke(
                        app,
                        [
                            "--connect", "test:///default",
                            "inject", "--yes", "--dry-run",
                            "--bandwidth", "2",
                            "disk.latency", "test",
                        ],
                    )
        assert result.exit_code == 0
```

Run:
```bash
uv run pytest tests/test_cli.py::TestBandwidthFlag -v
```

Expected: `test_disk_latency_appears_in_list_faults` passes; `test_bandwidth_flag_accepted` passes (dry-run skips actual cgroup writes)

- [ ] **Step 2.5: Add `--bandwidth` flag to `inject_cmd` in `cli.py`**

In `src/kvmchaos/cli.py`, add the import at the top (after existing fault imports):

```python
from kvmchaos.faults.disk_latency import DiskLatencyFault
```

Add `--bandwidth` parameter to `inject_cmd` (after the `duration` parameter):

```python
bandwidth: int = typer.Option(
    1,
    "--bandwidth",
    "-b",
    help="Disk throttle limit in MB/s (disk.latency only).",
    min=1,
),
```

Also update the docstring Args section:
```
bandwidth: Disk I/O throttle in MB/s, used only by disk.latency.
```

After the line `fault = FAULTS[fault_name]` (currently line ~159), add:

```python
    if fault_name == "disk.latency":
        fault = DiskLatencyFault(bandwidth_bps=bandwidth * 1_000_000)
```

- [ ] **Step 2.6: Run full test suite**

```bash
uv run pytest -q
```

Expected: all tests pass, coverage ≥85%

- [ ] **Step 2.7: Lint check**

```bash
uv run ruff check && uv run ruff format --check
```

Expected: `All checks passed!`

- [ ] **Step 2.8: Commit**

```bash
git add src/kvmchaos/faults/__init__.py src/kvmchaos/cli.py \
        tests/test_fault_local_only.py tests/test_cli.py
git commit -m "feat: register disk.latency fault and add --bandwidth CLI flag"
```

---

## Acceptance Checklist

After both tasks are committed, verify:

```bash
# Appears in list
uv run kvmchaos list-faults

# Dry-run (no cgroup writes, no sudo needed)
uv run kvmchaos inject disk.latency server1 --yes --dry-run

# Remote guard fires
uv run kvmchaos --connect qemu+ssh://192.168.0.99/system inject disk.latency server1 --yes
# Expected: exit 2, "requires local execution"

# Real inject (lab only, needs sudo)
sudo env PATH=$PATH uv run kvmchaos inject disk.latency server1 --bandwidth 2 --yes --duration 10
# Verify on guest during hold:
#   dd if=/dev/zero of=/tmp/test bs=1M count=100 oflag=direct
# Should take ~50s (2 MB/s limit). After revert, should take <1s.
```
