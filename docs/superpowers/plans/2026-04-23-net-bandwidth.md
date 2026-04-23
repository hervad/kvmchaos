# net.bandwidth Fault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `net.bandwidth` fault that caps a VM's first vNIC throughput to N kbps via `tc netem rate`, and extract the shared `_tap_device` helper from `net_latency.py` and `net_packet_loss.py` into `tc.py`.

**Architecture:** `NetBandwidthFault` mirrors `NetPacketLossFault` exactly — stateful class with `rate_kbps`, inject/verify/revert via the `tc` wrapper. A new `tc.add_netem_rate()` function and a public `tc.tap_device()` function are added to `tc.py`. The two existing net fault files are updated to import `tap_device` from `tc` instead of defining it locally.

**Tech Stack:** Python 3.14+, libvirt-python, typer, tc netem (iproute2), pytest, ruff.

---

## File Map

| Action | File | What changes |
|---|---|---|
| Modify | `src/kvmchaos/tc.py` | Add `add_netem_rate()`, add `tap_device()` |
| Modify | `src/kvmchaos/faults/net_latency.py` | Remove local `_tap_device`, import from `tc` |
| Modify | `src/kvmchaos/faults/net_packet_loss.py` | Remove local `_tap_device`, import from `tc` |
| Create | `src/kvmchaos/faults/net_bandwidth.py` | New fault class |
| Modify | `src/kvmchaos/faults/__init__.py` | Register `NetBandwidthFault` |
| Modify | `src/kvmchaos/cli.py` | Add `--rate` option, instantiate `NetBandwidthFault` |
| Modify | `tests/test_tc.py` | Add `TestAddNetemRate`, add `TestTapDevice` |
| Modify | `tests/test_faults_net_latency.py` | Update `_tap_device` import path |
| Modify | `tests/test_faults_net_packet_loss.py` | Update `_tap_device` import path |
| Create | `tests/test_faults_net_bandwidth.py` | Full test suite for new fault |
| Modify | `tests/test_cli.py` | Add `TestNetBandwidthCli` |

---

## Task 1: Extract `tap_device` into `tc.py` and add `add_netem_rate`

**Files:**
- Modify: `src/kvmchaos/tc.py`
- Modify: `tests/test_tc.py`

- [ ] **Step 1: Write failing tests for `tap_device` and `add_netem_rate` in `test_tc.py`**

Open `tests/test_tc.py` and append two new test classes at the bottom:

```python
class TestTapDevice:
    def test_returns_first_tap_device(self):
        xml = """
        <domain>
          <devices>
            <interface type='network'>
              <target dev='vnet0'/>
            </interface>
          </devices>
        </domain>
        """
        domain = MagicMock(spec=libvirt.virDomain)
        domain.name.return_value = "testvm"
        domain.XMLDesc.return_value = xml
        assert tc.tap_device(domain) == "vnet0"

    def test_raises_when_no_interface(self):
        domain = MagicMock(spec=libvirt.virDomain)
        domain.name.return_value = "testvm"
        domain.XMLDesc.return_value = "<domain><devices></devices></domain>"
        with pytest.raises(RuntimeError, match="no network interface"):
            tc.tap_device(domain)


class TestAddNetemRate:
    def test_calls_tc_with_correct_args(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            tc.add_netem_rate("vnet0", 1000)
        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "tc", "qdisc", "replace", "dev", "vnet0", "root", "netem", "rate", "1000kbit"
        ]

    def test_raises_on_tc_failure(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="RTNETLINK answers: No such file"
            )
            with pytest.raises(RuntimeError, match="tc command failed"):
                tc.add_netem_rate("vnet99", 1000)
```

Also add `import libvirt` to the imports at the top of `test_tc.py` (it's needed by `TestTapDevice`):

```python
import libvirt
import pytest

import kvmchaos.tc as tc
from unittest.mock import MagicMock, patch
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_tc.py::TestTapDevice tests/test_tc.py::TestAddNetemRate -v
```

Expected: `AttributeError: module 'kvmchaos.tc' has no attribute 'tap_device'`

- [ ] **Step 3: Add `tap_device` and `add_netem_rate` to `tc.py`**

Open `src/kvmchaos/tc.py`. Add the following imports at the top (after `from __future__ import annotations`):

```python
import xml.etree.ElementTree as ET

import libvirt
```

Then add the two new public functions after `add_netem_loss` and before `del_root_qdisc`:

```python
def add_netem_rate(dev: str, rate_kbps: int) -> None:
    """Add or replace a netem qdisc with a fixed rate limit on a network device.

    Uses ``replace`` so the call is idempotent if a qdisc already exists.

    Args:
        dev: Host network device name (e.g. ``'vnet0'``).
        rate_kbps: Bandwidth cap in kilobits per second.

    Raises:
        RuntimeError: If tc exits non-zero (e.g. device not found, no permission).
    """
    _run(["tc", "qdisc", "replace", "dev", dev, "root", "netem", "rate", f"{rate_kbps}kbit"])


def tap_device(domain: libvirt.virDomain) -> str:
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

- [ ] **Step 4: Run new tests to confirm they pass**

```bash
uv run pytest tests/test_tc.py::TestTapDevice tests/test_tc.py::TestAddNetemRate -v
```

Expected: both classes pass.

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
uv run pytest
```

Expected: same number of tests passing as before (288), no failures.

- [ ] **Step 6: Commit**

```bash
git add src/kvmchaos/tc.py tests/test_tc.py
git commit -m "feat(tc): add tap_device() and add_netem_rate()"
```

---

## Task 2: Update `net_latency.py` and `net_packet_loss.py` to use `tc.tap_device`

**Files:**
- Modify: `src/kvmchaos/faults/net_latency.py`
- Modify: `src/kvmchaos/faults/net_packet_loss.py`
- Modify: `tests/test_faults_net_latency.py`
- Modify: `tests/test_faults_net_packet_loss.py`

- [ ] **Step 1: Run existing net fault tests to establish baseline**

```bash
uv run pytest tests/test_faults_net_latency.py tests/test_faults_net_packet_loss.py -v
```

Expected: all pass. Note the count.

- [ ] **Step 2: Update `net_latency.py`**

Replace the entire file content with:

```python
"""`net.latency` fault — inject one-way latency on a VM's first virtual NIC.

Uses ``tc netem`` on the host-side tap device to add a fixed one-way delay.
The tap device name is resolved via :func:`kvmchaos.tc.tap_device`.

Requires root or CAP_NET_ADMIN on the host. All other faults are unaffected
by this privilege requirement.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt

import kvmchaos.tc as tc

_DELAY_MS: int = 200


class NetLatencyFault:
    """Injects one-way network latency via tc netem on the host tap device.

    Implements the ``Fault`` protocol — stateless, operates on a provided
    ``virDomain`` handle.
    """

    name: ClassVar[str] = "net.latency"
    description: ClassVar[str] = f"Add {_DELAY_MS}ms one-way latency to first vNIC via tc netem."
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply netem delay to the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_delay(tc.tap_device(domain), _DELAY_MS)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that a netem qdisc is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem is not present in tc qdisc show output.
        """
        dev = tc.tap_device(domain)
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
        tc.del_root_qdisc(tc.tap_device(domain))
```

- [ ] **Step 3: Update `net_packet_loss.py`**

Replace the entire file content with:

```python
"""`net.packet-loss` fault — inject packet loss on a VM's first virtual NIC.

Uses ``tc netem`` on the host-side tap device to drop a fixed percentage of
packets. The tap device name is resolved via :func:`kvmchaos.tc.tap_device`.

Requires root or CAP_NET_ADMIN on the host.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt

import kvmchaos.tc as tc

_DEFAULT_LOSS_PERCENT: int = 50


class NetPacketLossFault:
    """Injects packet loss via tc netem on the host tap device.

    Implements the ``Fault`` protocol. Stateful: ``loss_percent`` is set at
    construction and used across inject/verify/revert.
    """

    name: ClassVar[str] = "net.packet-loss"
    description: ClassVar[str] = (
        f"Drop {_DEFAULT_LOSS_PERCENT}% of packets on first vNIC via tc netem."
    )
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def __init__(self, loss_percent: int = _DEFAULT_LOSS_PERCENT) -> None:
        """Initialise with a packet-loss percentage.

        Args:
            loss_percent: Percentage of packets to drop (0-100). Default 50.
        """
        self.loss_percent = loss_percent

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply netem packet loss to the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_loss(tc.tap_device(domain), self.loss_percent)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that netem packet loss is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem is not present or loss is not configured.
        """
        dev = tc.tap_device(domain)
        output = tc.show_qdisc(dev)
        if "netem" not in output:
            raise RuntimeError(
                f"netem not active on '{dev}' for domain '{domain.name()}' after inject"
            )
        if "loss" not in output:
            raise RuntimeError(
                f"packet loss not active on '{dev}' for domain '{domain.name()}' after inject"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Remove the root qdisc from the tap device, restoring kernel default.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails.
        """
        tc.del_root_qdisc(tc.tap_device(domain))
```

- [ ] **Step 4: Run the net fault tests again**

```bash
uv run pytest tests/test_faults_net_latency.py tests/test_faults_net_packet_loss.py -v
```

Expected: same count as Step 1, all passing. The tests call through to `tc.tap_device` now — the XML parsing path is unchanged so behaviour is identical.

- [ ] **Step 5: Run ruff**

```bash
uv run ruff check && uv run ruff format --check
```

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/kvmchaos/faults/net_latency.py src/kvmchaos/faults/net_packet_loss.py
git commit -m "refactor(net): use tc.tap_device() in net_latency and net_packet_loss"
```

---

## Task 3: Implement `NetBandwidthFault`

**Files:**
- Create: `src/kvmchaos/faults/net_bandwidth.py`
- Create: `tests/test_faults_net_bandwidth.py`

- [ ] **Step 1: Write failing tests in `tests/test_faults_net_bandwidth.py`**

Create the file with this content:

```python
"""Tests for net.bandwidth fault."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import libvirt
import pytest

import kvmchaos.tc as tc
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


class TestNetBandwidthMetadata:
    def test_name(self):
        assert NetBandwidthFault.name == "net.bandwidth"

    def test_description_present(self):
        assert NetBandwidthFault.description

    def test_non_destructive(self):
        assert NetBandwidthFault.destructive is False

    def test_local_only(self):
        assert NetBandwidthFault.local_only is True

    def test_default_rate_kbps(self):
        assert NetBandwidthFault().rate_kbps == 1000

    def test_custom_rate_kbps(self):
        assert NetBandwidthFault(rate_kbps=512).rate_kbps == 512


class TestNetBandwidthHappyPath:
    def test_inject_calls_add_netem_rate(self):
        domain = _mock_domain()
        with patch.object(tc, "add_netem_rate") as mock_add:
            NetBandwidthFault().inject(domain)
        mock_add.assert_called_once_with("vnet0", 1000)

    def test_inject_passes_custom_rate(self):
        domain = _mock_domain()
        with patch.object(tc, "add_netem_rate") as mock_add:
            NetBandwidthFault(rate_kbps=256).inject(domain)
        mock_add.assert_called_once_with("vnet0", 256)

    def test_verify_passes_when_netem_rate_present(self):
        domain = _mock_domain()
        with patch.object(
            tc, "show_qdisc", return_value="qdisc netem 8001: root refcnt 2 rate 1000Kbit"
        ):
            NetBandwidthFault().verify(domain)  # must not raise

    def test_verify_raises_when_netem_absent(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "show_qdisc", return_value="qdisc pfifo_fast 0: root"),
            pytest.raises(RuntimeError, match="netem not active"),
        ):
            NetBandwidthFault().verify(domain)

    def test_verify_raises_when_rate_absent(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "show_qdisc", return_value="qdisc netem 8001: root delay 200ms"),
            pytest.raises(RuntimeError, match="bandwidth limit not active"),
        ):
            NetBandwidthFault().verify(domain)

    def test_revert_calls_del_root_qdisc(self):
        domain = _mock_domain()
        with patch.object(tc, "del_root_qdisc") as mock_del:
            NetBandwidthFault().revert(domain)
        mock_del.assert_called_once_with("vnet0")


class TestNetBandwidthErrorPaths:
    def test_inject_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with (
            patch.object(tc, "add_netem_rate"),
            pytest.raises(RuntimeError, match="no network interface"),
        ):
            NetBandwidthFault().inject(domain)

    def test_revert_raises_when_no_interface(self):
        domain = _mock_domain(_XML_NO_IFACE)
        with (
            patch.object(tc, "del_root_qdisc"),
            pytest.raises(RuntimeError, match="no network interface"),
        ):
            NetBandwidthFault().revert(domain)

    def test_inject_propagates_tc_error(self):
        domain = _mock_domain()
        with (
            patch.object(tc, "add_netem_rate", side_effect=RuntimeError("tc failed")),
            pytest.raises(RuntimeError, match="tc failed"),
        ):
            NetBandwidthFault().inject(domain)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_faults_net_bandwidth.py -v
```

Expected: `ModuleNotFoundError: No module named 'kvmchaos.faults.net_bandwidth'`

- [ ] **Step 3: Create `src/kvmchaos/faults/net_bandwidth.py`**

```python
"""`net.bandwidth` fault — cap a VM's first vNIC throughput via tc netem rate.

Uses ``tc netem rate`` on the host-side tap device to limit bandwidth to a
fixed number of kilobits per second. The tap device name is resolved via
:func:`kvmchaos.tc.tap_device`.

Requires root or CAP_NET_ADMIN on the host.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt

import kvmchaos.tc as tc

_DEFAULT_RATE_KBPS: int = 1000


class NetBandwidthFault:
    """Caps a VM's first vNIC throughput via tc netem rate on the host tap device.

    Implements the ``Fault`` protocol. Stateful: ``rate_kbps`` is set at
    construction and used across inject/verify/revert.
    """

    name: ClassVar[str] = "net.bandwidth"
    description: ClassVar[str] = (
        f"Cap first vNIC throughput to {_DEFAULT_RATE_KBPS}kbps via tc netem rate."
    )
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def __init__(self, rate_kbps: int = _DEFAULT_RATE_KBPS) -> None:
        """Initialise with a bandwidth cap.

        Args:
            rate_kbps: Throughput limit in kilobits per second. Default 1000.
        """
        self.rate_kbps = rate_kbps

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply netem rate limit to the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_rate(tc.tap_device(domain), self.rate_kbps)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that netem rate limiting is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem is not present or rate is not configured.
        """
        dev = tc.tap_device(domain)
        output = tc.show_qdisc(dev)
        if "netem" not in output:
            raise RuntimeError(
                f"netem not active on '{dev}' for domain '{domain.name()}' after inject"
            )
        if "rate" not in output:
            raise RuntimeError(
                f"bandwidth limit not active on '{dev}' for domain '{domain.name()}' after inject"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Remove the root qdisc from the tap device, restoring kernel default.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails.
        """
        tc.del_root_qdisc(tc.tap_device(domain))
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_faults_net_bandwidth.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/kvmchaos/faults/net_bandwidth.py tests/test_faults_net_bandwidth.py
git commit -m "feat(fault): add net.bandwidth — cap vNIC throughput via tc netem rate"
```

---

## Task 4: Register fault, wire CLI, add CLI test

**Files:**
- Modify: `src/kvmchaos/faults/__init__.py`
- Modify: `src/kvmchaos/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI test**

Open `tests/test_cli.py`. Find the `TestNetPartitionCli` class near the bottom and insert the following class **before** it:

```python
class TestNetBandwidthCli:
    def test_net_bandwidth_appears_in_list_faults(self) -> None:
        result = runner.invoke(app, ["list-faults"])
        assert result.exit_code == 0
        assert "net.bandwidth" in result.stdout

    def test_rate_flag_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock, patch

        from kvmchaos.faults.net_bandwidth import NetBandwidthFault

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

        def capturing_run_step(func, domain, *, action, fault_name, vm, dry_run=False):
            return {"action": action, "result": "skipped", "duration_ms": 0}

        with (
            patch("kvmchaos.cli._run_step", side_effect=capturing_run_step),
            patch("kvmchaos.cli.FAULTS", {"net.bandwidth": NetBandwidthFault()}),
            patch("kvmchaos.cli.connect") as mock_conn,
        ):
            mock_domain = MagicMock()
            mock_conn.return_value.__enter__.return_value.lookupByName.return_value = mock_domain
            result = runner.invoke(
                app,
                [
                    "--connect",
                    "test:///default",
                    "inject",
                    "--yes",
                    "--dry-run",
                    "--rate",
                    "512",
                    "net.bandwidth",
                    "test",
                ],
            )
        assert result.exit_code == 0
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
uv run pytest tests/test_cli.py::TestNetBandwidthCli -v
```

Expected: `assert "net.bandwidth" in result.stdout` fails — fault not registered yet.

- [ ] **Step 3: Register `NetBandwidthFault` in `faults/__init__.py`**

Open `src/kvmchaos/faults/__init__.py`. Add the import and registry entry:

```python
from kvmchaos.faults.net_bandwidth import NetBandwidthFault
```

Add to the `FAULTS` dict (after `NetPartitionFault`):

```python
NetBandwidthFault.name: NetBandwidthFault(),
```

The full updated `FAULTS` dict should look like:

```python
FAULTS: dict[str, Fault] = {
    VmPauseFault.name: VmPauseFault(),
    VmKillFault.name: VmKillFault(),
    VmFreezeFault.name: VmFreezeFault(),
    VmStarveFault.name: VmStarveFault(),
    NetLatencyFault.name: NetLatencyFault(),
    DiskLatencyFault.name: DiskLatencyFault(),
    DiskFillFault.name: DiskFillFault(),
    NetPacketLossFault.name: NetPacketLossFault(),
    ClockSkewFault.name: ClockSkewFault(),
    NetPartitionFault.name: NetPartitionFault(),
    NetBandwidthFault.name: NetBandwidthFault(),
}
```

- [ ] **Step 4: Add `--rate` to `inject_cmd` in `cli.py`**

Open `src/kvmchaos/cli.py`.

Add the import at the top with the other fault imports:

```python
from kvmchaos.faults.net_bandwidth import NetBandwidthFault
```

Add the `--rate` option to `inject_cmd` after the `--loss` option:

```python
rate: int = typer.Option(
    1000,
    "--rate",
    help="Bandwidth cap in kbps (net.bandwidth only).",
    min=1,
),
```

Add `rate` to the `inject_cmd` signature docstring Args block:

```
rate: Bandwidth cap in kbps, used only by net.bandwidth.
```

Add the `net.bandwidth` branch in the fault instantiation block (after the `net.packet-loss` branch):

```python
elif fault_name == "net.bandwidth":
    fault = NetBandwidthFault(rate_kbps=rate)
```

- [ ] **Step 5: Run the CLI tests**

```bash
uv run pytest tests/test_cli.py::TestNetBandwidthCli -v
```

Expected: both tests pass.

- [ ] **Step 6: Run ruff**

```bash
uv run ruff check && uv run ruff format --check
```

Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/kvmchaos/faults/__init__.py src/kvmchaos/cli.py tests/test_cli.py
git commit -m "feat(cli): register net.bandwidth fault and wire --rate flag"
```

---

## Task 5: Final verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest
```

Expected: all tests pass, coverage ≥ 85%.

- [ ] **Step 2: Verify `list-faults` output**

```bash
uv run kvmchaos list-faults
```

Expected: `net.bandwidth` appears in the list with `[safe       ]` marker.

- [ ] **Step 3: Run ruff one final time**

```bash
uv run ruff check && uv run ruff format --check
```

Expected: `All checks passed!`

- [ ] **Step 4: Update PLAN.md acceptance criteria**

Open `PLAN.md`. Add a new `## Acceptance (v0.13)` section after the v0.12 section:

```markdown
## Acceptance (v0.13)

- [ ] `net.bandwidth` registered in `list-faults` with `local_only = True`
- [ ] `kvmchaos inject net.bandwidth <vm> --rate N` caps VM NIC throughput to N kbps via tc netem rate
- [ ] Revert removes root qdisc, restoring normal forwarding
- [ ] `_tap_device` extracted to `tc.tap_device()`; `net_latency` and `net_packet_loss` use it
- [ ] `pytest` passes with coverage ≥85%
- [ ] `ruff check`, `ruff format --check` clean
- [ ] Lab validation on Fedora 43 KVM host
```

- [ ] **Step 5: Commit PLAN.md**

```bash
git add PLAN.md
git commit -m "docs: add v0.13 acceptance criteria for net.bandwidth"
```
