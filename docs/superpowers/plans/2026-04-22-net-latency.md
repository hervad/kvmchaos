# net.latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `net.latency` fault that injects 200ms RTT latency on a VM's first virtual NIC using `tc netem` on the host, observable with `ping` from a second VM.

**Architecture:** A new `tc.py` module wraps subprocess calls to `tc` and is imported by `NetLatencyFault`. The fault extracts the host-side tap device name from domain XML, applies/removes a netem qdisc, and verifies via `tc qdisc show`. All tc calls in tests are mocked via `unittest.mock.patch`.

**Tech Stack:** `tc` (iproute2, already on Fedora 43 host), `xml.etree.ElementTree` (stdlib), `subprocess` (stdlib), `libvirt-python`.

**Privilege note:** `tc qdisc` requires root or `CAP_NET_ADMIN` on the host. `kvmchaos` must be run as root or via `sudo` for this fault. All other faults are unaffected.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/kvmchaos/tc.py` | Thin subprocess wrapper for `tc` commands |
| Create | `src/kvmchaos/faults/net_latency.py` | `NetLatencyFault` implementation |
| Modify | `src/kvmchaos/faults/__init__.py` | Register `net.latency` |
| Create | `tests/test_tc.py` | Unit tests for `tc.py` |
| Create | `tests/test_faults_net_latency.py` | Unit tests for `NetLatencyFault` |

---

## Task 1: tc subprocess wrapper

**Files:**
- Create: `src/kvmchaos/tc.py`
- Create: `tests/test_tc.py`

- [ ] **Step 1: Write failing tests for tc.py**

```python
# tests/test_tc.py
"""Unit tests for the tc subprocess wrapper."""

from unittest.mock import MagicMock, patch

import pytest

import kvmchaos.tc as tc


class TestAddNetemDelay:
    def test_calls_tc_with_correct_args(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            tc.add_netem_delay("vnet0", 200)
            mock_run.assert_called_once_with(
                ["tc", "qdisc", "replace", "dev", "vnet0", "root", "netem", "delay", "200ms"],
                capture_output=True,
                text=True,
            )

    def test_raises_runtime_error_on_nonzero_exit(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="RTNETLINK error")
            with pytest.raises(RuntimeError, match="tc command failed"):
                tc.add_netem_delay("vnet0", 200)


class TestDelRootQdisc:
    def test_calls_tc_with_correct_args(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            tc.del_root_qdisc("vnet0")
            mock_run.assert_called_once_with(
                ["tc", "qdisc", "del", "dev", "vnet0", "root"],
                capture_output=True,
                text=True,
            )

    def test_raises_runtime_error_on_nonzero_exit(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="No such file")
            with pytest.raises(RuntimeError, match="tc command failed"):
                tc.del_root_qdisc("vnet0")


class TestShowQdisc:
    def test_returns_stdout(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="qdisc netem 8001: root", stderr="")
            result = tc.show_qdisc("vnet0")
            assert result == "qdisc netem 8001: root"

    def test_does_not_raise_on_nonzero_exit(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="no device")
            result = tc.show_qdisc("vnet0")
            assert result == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_tc.py -v
```
Expected: `ModuleNotFoundError: No module named 'kvmchaos.tc'`

- [ ] **Step 3: Implement tc.py**

```python
# src/kvmchaos/tc.py
"""Thin subprocess wrapper for tc (iproute2) qdisc commands.

All functions that mutate qdisc state require root or CAP_NET_ADMIN on
the host. A non-zero exit from tc raises RuntimeError with the stderr output.
"""

from __future__ import annotations

import subprocess


def add_netem_delay(dev: str, delay_ms: int) -> None:
    """Add or replace a netem qdisc with a fixed delay on a network device.

    Uses ``replace`` so the call is idempotent if a qdisc already exists.

    Args:
        dev: Host network device name (e.g. ``'vnet0'``).
        delay_ms: One-way delay in milliseconds.

    Raises:
        RuntimeError: If tc exits non-zero (e.g. device not found, no permission).
    """
    _run(["tc", "qdisc", "replace", "dev", dev, "root", "netem", "delay", f"{delay_ms}ms"])


def del_root_qdisc(dev: str) -> None:
    """Remove the root qdisc from a network device, restoring the kernel default.

    Args:
        dev: Host network device name.

    Raises:
        RuntimeError: If tc exits non-zero.
    """
    _run(["tc", "qdisc", "del", "dev", dev, "root"])


def show_qdisc(dev: str) -> str:
    """Return the output of ``tc qdisc show dev <dev>``.

    Never raises — returns empty string on failure so callers can
    inspect without catching exceptions.

    Args:
        dev: Host network device name.

    Returns:
        Raw stdout from tc, or empty string if tc fails.
    """
    result = subprocess.run(
        ["tc", "qdisc", "show", "dev", dev],
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def _run(cmd: list[str]) -> None:
    """Run a tc command, raising RuntimeError on non-zero exit.

    Args:
        cmd: Full command list including ``'tc'`` as first element.

    Raises:
        RuntimeError: If the command exits non-zero.
    """
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"tc command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_tc.py -v
```
Expected: all 6 tests pass.

- [ ] **Step 5: Lint**

```bash
uv run ruff check src/kvmchaos/tc.py tests/test_tc.py && uv run ruff format --check src/kvmchaos/tc.py tests/test_tc.py
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/kvmchaos/tc.py tests/test_tc.py
git commit -m "feat: add tc subprocess wrapper for netem qdisc commands"
```

---

## Task 2: NetLatencyFault

**Files:**
- Create: `src/kvmchaos/faults/net_latency.py`
- Create: `tests/test_faults_net_latency.py`

The fault extracts the first `<target dev="...">` from the domain XML to get the host-side tap device (e.g. `vnet0`), then delegates to `tc.py`.

Domain XML fragment for reference:
```xml
<interface type='network'>
  <target dev='vnet0'/>
</interface>
```

- [ ] **Step 1: Write failing tests**

```python
# tests/test_faults_net_latency.py
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
        with patch.object(tc, "show_qdisc", return_value="qdisc fq_codel 0: root"):
            with pytest.raises(RuntimeError, match="netem not active"):
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
        with patch.object(tc, "add_netem_delay", side_effect=RuntimeError("tc failed")):
            with pytest.raises(RuntimeError, match="tc failed"):
                NetLatencyFault().inject(domain)

    def test_revert_propagates_tc_error(self):
        domain = _mock_domain()
        with patch.object(tc, "del_root_qdisc", side_effect=RuntimeError("tc failed")):
            with pytest.raises(RuntimeError, match="tc failed"):
                NetLatencyFault().revert(domain)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_faults_net_latency.py -v
```
Expected: `ModuleNotFoundError: No module named 'kvmchaos.faults.net_latency'`

- [ ] **Step 3: Implement net_latency.py**

```python
# src/kvmchaos/faults/net_latency.py
"""`net.latency` fault — inject RTT latency on a VM's first virtual NIC.

Uses ``tc netem`` on the host-side tap device to add a fixed one-way delay.
The tap device name is read from the domain XML ``<target dev="..."/>``
attribute, which libvirt keeps in sync with the running QEMU process.

Requires root or CAP_NET_ADMIN on the host. All other faults are unaffected
by this privilege requirement.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import ClassVar

import libvirt

import kvmchaos.tc as tc

_DELAY_MS: int = 200


class NetLatencyFault:
    """Injects one-way network latency via tc netem on the host tap device.

    Implements the `Fault` protocol — stateless, operates on a provided
    `virDomain` handle.
    """

    name: ClassVar[str] = "net.latency"
    description: ClassVar[str] = f"Add {_DELAY_MS}ms RTT latency to first vNIC via tc netem."
    destructive: ClassVar[bool] = False

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply netem delay to the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_delay(_tap_device(domain), _DELAY_MS)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that a netem qdisc is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem is not present in tc qdisc show output.
        """
        dev = _tap_device(domain)
        output = tc.show_qdisc(dev)
        if "netem" not in output:
            raise RuntimeError(
                f"netem not active on '{dev}' for domain '{domain.name()}' after inject"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Remove the root qdisc from the tap device, restoring kernel default.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails.
        """
        tc.del_root_qdisc(_tap_device(domain))


def _tap_device(domain: libvirt.virDomain) -> str:
    """Extract the first tap device name from the domain XML.

    Parses the ``<target dev="..."/>`` attribute of the first ``<interface>``
    element in the domain XML descriptor.

    Args:
        domain: A live libvirt domain handle.

    Returns:
        Host-side tap device name (e.g. ``'vnet0'``).

    Raises:
        RuntimeError: If no ``<interface>`` with a ``<target dev>`` is found.
    """
    root = ET.fromstring(domain.XMLDesc())
    target = root.find(".//interface/target[@dev]")
    if target is None:
        raise RuntimeError(f"no network interface found for domain '{domain.name()}'")
    return target.attrib["dev"]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_faults_net_latency.py -v
```
Expected: all 10 tests pass.

- [ ] **Step 5: Lint**

```bash
uv run ruff check src/kvmchaos/faults/net_latency.py tests/test_faults_net_latency.py
uv run ruff format --check src/kvmchaos/faults/net_latency.py tests/test_faults_net_latency.py
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/kvmchaos/faults/net_latency.py tests/test_faults_net_latency.py
git commit -m "feat: add NetLatencyFault — tc netem on host tap device"
```

---

## Task 3: Register the fault and full suite

**Files:**
- Modify: `src/kvmchaos/faults/__init__.py`

- [ ] **Step 1: Register net.latency**

In `src/kvmchaos/faults/__init__.py`, add the import and registry entry:

```python
from kvmchaos.faults.net_latency import NetLatencyFault

FAULTS: dict[str, Fault] = {
    VmPauseFault.name: VmPauseFault(),
    VmKillFault.name: VmKillFault(),
    VmFreezeFault.name: VmFreezeFault(),
    VmStarveFault.name: VmStarveFault(),
    NetLatencyFault.name: NetLatencyFault(),
}
```

- [ ] **Step 2: Confirm list-faults shows net.latency**

```bash
uv run kvmchaos list-faults
```
Expected output includes:
```
net.latency  [safe       ]  Add 200ms RTT latency to first vNIC via tc netem.
```

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest -q
```
Expected: all tests pass, coverage ≥85%.

- [ ] **Step 4: Run linters**

```bash
uv run ruff check && uv run ruff format --check
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add src/kvmchaos/faults/__init__.py
git commit -m "feat: register net.latency fault"
```

---

## Lab Validation

Run on the Fedora 43 host as root (or with sudo). Observe from the second VM.

**Terminal A (host, root):**
```bash
sudo uv run kvmchaos inject net.latency server1 --yes
```

**Terminal B (server2 guest, while fault is held):**
```bash
ping -c 10 <server1-ip>
```
Expected: RTT ~200ms. Before/after: normal LAN RTT (<1ms).

**Confirm revert (Terminal B, after hold):**
```bash
ping -c 5 <server1-ip>
```
Expected: RTT back to normal.

**Check the host tap device directly (Terminal A):**
```bash
tc qdisc show dev vnet0   # during hold: shows netem delay 200ms
tc qdisc show dev vnet0   # after revert: shows default qdisc only
```
