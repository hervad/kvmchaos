# net.corrupt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `net.corrupt` fault that injects random bit corruption into a VM's first vNIC packets via `tc netem corrupt N%` on the host-side tap device.

**Architecture:** Follows the identical pattern as `net.packet-loss` and `net.bandwidth` — a new `add_netem_corrupt()` in `tc.py`, a new `NetCorruptFault` class in `faults/net_corrupt.py`, registration in `faults/__init__.py`, and a `--corrupt` flag wired into `inject_cmd` in `cli.py`.

**Tech Stack:** Python 3.14, `tc` (iproute2), `libvirt-python`, `typer`, `pytest`.

---

## File Map

| Action | File |
|--------|------|
| Modify | `src/kvmchaos/tc.py` — add `add_netem_corrupt()` |
| Create | `src/kvmchaos/faults/net_corrupt.py` — new fault class |
| Modify | `src/kvmchaos/faults/__init__.py` — register `NetCorruptFault` |
| Modify | `src/kvmchaos/cli.py` — add `--corrupt` flag and branch |
| Modify | `tests/test_tc.py` — add `TestAddNetemCorrupt` |
| Create | `tests/test_faults_net_corrupt.py` — full fault test suite |
| Modify | `tests/test_cli.py` — add `TestNetCorruptCli` |

---

## Task 1: Add `add_netem_corrupt()` to tc.py

**Files:**
- Modify: `src/kvmchaos/tc.py`
- Modify: `tests/test_tc.py`

- [ ] **Step 1: Write the failing test**

Add this class to `tests/test_tc.py` (after `TestAddNetemRate`):

```python
class TestAddNetemCorrupt:
    def test_calls_tc_with_correct_args(self, mock_run: MagicMock) -> None:
        tc.add_netem_corrupt("vnet0", 5)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "replace", "dev", "vnet0", "root", "netem", "corrupt", "5%"]
        )

    def test_raises_on_nonzero_exit(self) -> None:
        with (
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=1, stderr="Operation not permitted"),
            ),
            pytest.raises(RuntimeError, match="Operation not permitted"),
        ):
            tc.add_netem_corrupt("vnet0", 5)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
uv run pytest tests/test_tc.py::TestAddNetemCorrupt -v
```

Expected: `FAILED` — `AttributeError: module 'kvmchaos.tc' has no attribute 'add_netem_corrupt'`

- [ ] **Step 3: Implement `add_netem_corrupt` in tc.py**

Add after `add_netem_loss()`:

```python
def add_netem_corrupt(dev: str, corrupt_percent: int) -> None:
    """Add or replace a netem qdisc with a fixed packet-corruption rate on a network device.

    Uses ``replace`` so the call is idempotent if a qdisc already exists.

    Args:
        dev: Host network device name (e.g. ``'vnet0'``).
        corrupt_percent: Percentage of packets to corrupt (1–100).

    Raises:
        RuntimeError: If tc exits non-zero (e.g. device not found, no permission).
    """
    _run(["tc", "qdisc", "replace", "dev", dev, "root", "netem", "corrupt", f"{corrupt_percent}%"])
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
uv run pytest tests/test_tc.py::TestAddNetemCorrupt -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/kvmchaos/tc.py tests/test_tc.py
git commit -m "feat(tc): add add_netem_corrupt() for packet corruption"
```

---

## Task 2: Implement `NetCorruptFault`

**Files:**
- Create: `src/kvmchaos/faults/net_corrupt.py`
- Create: `tests/test_faults_net_corrupt.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_faults_net_corrupt.py`:

```python
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
            patch.object(tc, "add_netem_corrupt", side_effect=RuntimeError("Operation not permitted")),
            pytest.raises(RuntimeError, match="Operation not permitted"),
        ):
            NetCorruptFault().inject(domain)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_faults_net_corrupt.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'kvmchaos.faults.net_corrupt'`

- [ ] **Step 3: Implement `NetCorruptFault`**

Create `src/kvmchaos/faults/net_corrupt.py`:

```python
"""`net.corrupt` fault — inject packet corruption on a VM's first virtual NIC.

Uses ``tc netem corrupt N%`` on the host-side tap device to corrupt a fixed
percentage of packets. The tap device name is resolved via
:func:`kvmchaos.tc.tap_device`.

Requires root or CAP_NET_ADMIN on the host.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt

import kvmchaos.tc as tc

_DEFAULT_CORRUPT_PERCENT: int = 1


class NetCorruptFault:
    """Injects random bit corruption into a VM's first vNIC packets via tc netem.

    Implements the ``Fault`` protocol. Stateful: ``corrupt_percent`` is set at
    construction and used across inject/verify/revert.
    """

    name: ClassVar[str] = "net.corrupt"
    description: ClassVar[str] = (
        f"Corrupt {_DEFAULT_CORRUPT_PERCENT}% of packets on first vNIC via tc netem corrupt."
    )
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def __init__(self, corrupt_percent: int = _DEFAULT_CORRUPT_PERCENT) -> None:
        """Initialise with a corruption percentage.

        Args:
            corrupt_percent: Percentage of packets to corrupt (1–100). Default 1.
        """
        self.corrupt_percent = corrupt_percent

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply netem corrupt rule to the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_corrupt(tc.tap_device(domain), self.corrupt_percent)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that netem packet corruption is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem is not present or corrupt is not configured.
        """
        dev = tc.tap_device(domain)
        output = tc.show_qdisc(dev)
        if "netem" not in output:
            raise RuntimeError(
                f"netem not active on '{dev}' for domain '{domain.name()}' after inject"
            )
        if "corrupt" not in output:
            raise RuntimeError(
                f"corruption not active on '{dev}' for domain '{domain.name()}' after inject"
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
uv run pytest tests/test_faults_net_corrupt.py -v
```

Expected: `13 passed`

- [ ] **Step 5: Commit**

```bash
git add src/kvmchaos/faults/net_corrupt.py tests/test_faults_net_corrupt.py
git commit -m "feat(faults): add NetCorruptFault via tc netem corrupt"
```

---

## Task 3: Register fault and wire CLI

**Files:**
- Modify: `src/kvmchaos/faults/__init__.py`
- Modify: `src/kvmchaos/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add this class to `tests/test_cli.py` (after `TestNetBandwidthCli`):

```python
class TestNetCorruptCli:
    def test_net_corrupt_appears_in_list_faults(self) -> None:
        result = runner.invoke(app, ["list-faults"])
        assert result.exit_code == 0
        assert "net.corrupt" in result.stdout

    def test_corrupt_flag_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock, patch

        from kvmchaos.faults.net_corrupt import NetCorruptFault

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

        def capturing_run_step(func, domain, *, action, fault_name, vm, dry_run=False):
            return {"action": action, "result": "skipped", "duration_ms": 0}

        with (
            patch("kvmchaos.cli._run_step", side_effect=capturing_run_step),
            patch("kvmchaos.cli.FAULTS", {"net.corrupt": NetCorruptFault()}),
            patch("kvmchaos.cli.connect") as mock_conn,
        ):
            mock_domain = MagicMock()
            mock_conn.return_value.__enter__.return_value.lookupByName.return_value = mock_domain
            result = runner.invoke(
                app,
                [
                    "inject",
                    "--yes",
                    "--dry-run",
                    "--corrupt",
                    "5",
                    "net.corrupt",
                    "test",
                ],
            )
        assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_cli.py::TestNetCorruptCli -v
```

Expected: `FAILED` — `net.corrupt` not in list-faults output, `--corrupt` unrecognised option.

- [ ] **Step 3: Register `NetCorruptFault` in `faults/__init__.py`**

Add import after `NetBandwidthFault`:

```python
from kvmchaos.faults.net_corrupt import NetCorruptFault
```

Add to `FAULTS` dict after `NetBandwidthFault.name`:

```python
NetCorruptFault.name: NetCorruptFault(),
```

- [ ] **Step 4: Add `--corrupt` flag and branch to `cli.py`**

Add import after `NetBandwidthFault`:

```python
from kvmchaos.faults.net_corrupt import NetCorruptFault
```

Add option after the `--rate` option in `inject_cmd`:

```python
corrupt: int = typer.Option(
    1,
    "--corrupt",
    help="Packet corruption percentage (net.corrupt only).",
    min=1,
    max=100,
),
```

Add to the docstring Args block after `rate`:

```
corrupt: Packet corruption percentage, used only by net.corrupt.
```

Add branch after the `net.bandwidth` branch in the fault instantiation block:

```python
elif fault_name == "net.corrupt":
    fault = NetCorruptFault(corrupt_percent=corrupt)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
uv run pytest tests/test_cli.py::TestNetCorruptCli -v
```

Expected: `2 passed`

- [ ] **Step 6: Run full suite**

```bash
uv run pytest -q
```

Expected: all tests pass, coverage ≥85%.

- [ ] **Step 7: Lint and format check**

```bash
uv run ruff check && uv run ruff format --check
```

Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/kvmchaos/faults/__init__.py src/kvmchaos/cli.py tests/test_cli.py
git commit -m "feat(cli): register net.corrupt fault and wire --corrupt flag"
```

---

## Task 4: Lab validation and acceptance tick

- [ ] **Step 1: Start server1 if not running**

```bash
virsh --connect qemu+ssh://localhost/system start server1
```

- [ ] **Step 2: Verify `net.corrupt` appears in list-faults**

```bash
uv run kvmchaos list-faults | grep corrupt
```

Expected: `net.corrupt    [safe       ]  Corrupt 1% of packets on first vNIC via tc netem corrupt.`

- [ ] **Step 3: Inject with sudo**

```bash
sudo /home/kai/kvmchaos/.venv/bin/kvmchaos inject net.corrupt server1 --corrupt 5 --yes --duration 5
```

Expected: `Holding 'net.corrupt' on 'server1' for 5s …` followed by run record path.

- [ ] **Step 4: Read the run record**

```bash
sudo cat /home/kai/.local/state/kvmchaos/runs/<latest>.json
```

Expected: `"outcome": "success"`, all three steps `"result": "ok"`.

- [ ] **Step 5: Verify local-only rejection**

```bash
uv run kvmchaos --connect qemu+ssh://192.168.0.99/system inject net.corrupt server1 --yes 2>&1
```

Expected: exit 2 with `requires local execution`.

- [ ] **Step 6: Tick acceptance criteria in PLAN.md**

In `PLAN.md`, find the `## Acceptance (v0.14) — net.corrupt` section (add it if not present, after v0.13) and tick all boxes:

```markdown
## Acceptance (v0.14) — net.corrupt

- [x] `net.corrupt` registered in `list-faults` with `local_only = True`
- [x] `kvmchaos inject net.corrupt <vm> --corrupt N` corrupts N% of packets on VM's first vNIC
- [x] Revert removes the root qdisc, restoring normal forwarding
- [x] `pytest` passes with coverage ≥85%
- [x] `ruff check`, `ruff format --check` clean
- [x] Lab validation on Fedora 43 KVM host (2026-04-23)
```

- [ ] **Step 7: Update RESUME.md**

Update `docs/superpowers/RESUME.md` — add v0.14 entry under "What's done", update repo state (test count, coverage), update "What's next".

- [ ] **Step 8: Commit**

```bash
git add PLAN.md docs/superpowers/RESUME.md
git commit -m "docs: tick v0.14 net.corrupt acceptance and update RESUME"
```

- [ ] **Step 9: Tag**

```bash
git tag v0.14.0
```
