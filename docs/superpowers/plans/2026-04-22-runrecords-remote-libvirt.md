# Run Records + Remote libvirt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-run JSON record files to every `inject` invocation and guard `net.latency` from silently misfiring against remote KVM hosts.

**Architecture:** Tasks 1 and 2 are fully independent — run in parallel. Task 3 depends on Task 2 (adds remote guard to CLI). Task 4 depends on Tasks 1 and 3 (adds run record collection to CLI). Task 5 is final cleanup and lab checklist.

**Tech Stack:** Python 3.14, `urllib.parse` (stdlib), `json` (stdlib), `typer`, `libvirt-python`, `pytest`.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `src/kvmchaos/runrecord.py` | Create | `default_runs_dir()` and `write_run_record()` |
| `src/kvmchaos/faults/base.py` | Modify | Add `local_only: bool` to `Fault` Protocol |
| `src/kvmchaos/faults/vm_pause.py` | Modify | Add `local_only: ClassVar[bool] = False` |
| `src/kvmchaos/faults/vm_kill.py` | Modify | Add `local_only: ClassVar[bool] = False` |
| `src/kvmchaos/faults/vm_freeze.py` | Modify | Add `local_only: ClassVar[bool] = False` |
| `src/kvmchaos/faults/vm_starve.py` | Modify | Add `local_only: ClassVar[bool] = False` |
| `src/kvmchaos/faults/net_latency.py` | Modify | Add `local_only: ClassVar[bool] = True` |
| `src/kvmchaos/cli.py` | Modify | `_is_remote()`, remote guard, `_run_step` returns dict, `_write_and_print_record()`, collect steps in `inject_cmd` |
| `tests/test_runrecord.py` | Create | Unit tests for `runrecord` module |
| `tests/test_fault_local_only.py` | Create | Unit tests for `local_only` attribute on all faults |
| `tests/test_remote_guard.py` | Create | Unit tests for `_is_remote` and CLI guard |
| `tests/test_cli.py` | Modify | Add `TestRunRecord` integration tests |
| `PLAN.md` | Modify | Add lab validation checklist for v0.3 |

---

## Task 1: `runrecord` module

> Independent of Task 2. Can run in parallel with Task 2.

**Files:**
- Create: `src/kvmchaos/runrecord.py`
- Create: `tests/test_runrecord.py`

- [ ] **Step 1.1: Write failing tests**

Create `tests/test_runrecord.py`:

```python
"""Unit tests for the runrecord module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kvmchaos.runrecord import default_runs_dir, write_run_record

_SAMPLE: dict[str, object] = {
    "started_at": "2026-04-22T16:30:00+00:00",
    "ended_at": "2026-04-22T16:30:22+00:00",
    "fault": "vm.freeze",
    "vm": "server1",
    "uri": "qemu:///system",
    "dry_run": False,
    "duration_s": 22,
    "outcome": "success",
    "steps": [
        {"action": "inject", "result": "ok", "duration_ms": 12},
        {"action": "verify", "result": "ok", "duration_ms": 8},
        {"action": "revert", "result": "ok", "duration_ms": 10},
    ],
}


class TestDefaultRunsDir:
    def test_default_without_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        assert default_runs_dir() == Path.home() / ".local" / "state" / "kvmchaos" / "runs"

    def test_respects_xdg_state_home(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        assert default_runs_dir() == tmp_path / "kvmchaos" / "runs"


class TestWriteRunRecord:
    def test_creates_directory(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / "runs"
        assert not runs_dir.exists()
        write_run_record(_SAMPLE, runs_dir)
        assert runs_dir.is_dir()

    def test_filename_format(self, tmp_path: Path) -> None:
        path = write_run_record(_SAMPLE, tmp_path)
        assert path.name == "20260422T163000Z-vm-freeze-server1.json"

    def test_dot_to_hyphen_in_fault_name(self, tmp_path: Path) -> None:
        record = {**_SAMPLE, "fault": "net.latency", "vm": "server2"}
        path = write_run_record(record, tmp_path)
        assert "net-latency" in path.name
        assert "." not in path.stem

    def test_content_roundtrips(self, tmp_path: Path) -> None:
        path = write_run_record(_SAMPLE, tmp_path)
        loaded = json.loads(path.read_text())
        assert loaded["fault"] == "vm.freeze"
        assert loaded["vm"] == "server1"
        assert loaded["outcome"] == "success"
        assert len(loaded["steps"]) == 3

    def test_returns_written_path(self, tmp_path: Path) -> None:
        path = write_run_record(_SAMPLE, tmp_path)
        assert path.exists()
        assert path.suffix == ".json"
```

- [ ] **Step 1.2: Run tests and confirm they fail**

```bash
cd /home/kai/kvmchaos
uv run pytest tests/test_runrecord.py -v
```

Expected: `ModuleNotFoundError: No module named 'kvmchaos.runrecord'`

- [ ] **Step 1.3: Implement `src/kvmchaos/runrecord.py`**

Create `src/kvmchaos/runrecord.py`:

```python
"""Per-run JSON record writer for kvmchaos.

Writes one JSON file per inject invocation to a XDG-compliant directory.
Each file contains the full lifecycle of a single inject run: fault, VM,
URI, timestamps, per-step outcomes, and overall result.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def default_runs_dir() -> Path:
    """Return the XDG-compliant default directory for per-run JSON records.

    Returns:
        Path under ``$XDG_STATE_HOME/kvmchaos/runs/``, defaulting to
        ``~/.local/state/kvmchaos/runs/`` when ``XDG_STATE_HOME`` is unset.
    """
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "kvmchaos" / "runs"


def write_run_record(record: dict[str, object], runs_dir: Path) -> Path:
    """Serialise a run record to a timestamped JSON file.

    File name format: ``{compact_ts}-{fault_slug}-{vm}.json``.
    Dots in fault names are replaced with hyphens (e.g. ``vm.freeze`` →
    ``vm-freeze``) to avoid ambiguous file extensions.

    Args:
        record: Run record dict. Must include ``started_at``, ``fault``, ``vm``.
        runs_dir: Directory to write into. Created if it does not exist.

    Returns:
        Absolute path of the written JSON file.
    """
    runs_dir.mkdir(parents=True, exist_ok=True)
    dt = datetime.fromisoformat(str(record["started_at"]))
    compact = dt.strftime("%Y%m%dT%H%M%SZ")
    fault_slug = str(record["fault"]).replace(".", "-")
    filename = f"{compact}-{fault_slug}-{record['vm']}.json"
    path = runs_dir / filename
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path
```

- [ ] **Step 1.4: Run tests and confirm they pass**

```bash
uv run pytest tests/test_runrecord.py -v
```

Expected: 7 tests pass.

- [ ] **Step 1.5: Commit**

```bash
git add src/kvmchaos/runrecord.py tests/test_runrecord.py
git commit -m "feat: add runrecord module for per-run JSON records"
```

---

## Task 2: `local_only` attribute on all fault classes

> Independent of Task 1. Can run in parallel with Task 1.

**Files:**
- Create: `tests/test_fault_local_only.py`
- Modify: `src/kvmchaos/faults/base.py`
- Modify: `src/kvmchaos/faults/vm_pause.py`
- Modify: `src/kvmchaos/faults/vm_kill.py`
- Modify: `src/kvmchaos/faults/vm_freeze.py`
- Modify: `src/kvmchaos/faults/vm_starve.py`
- Modify: `src/kvmchaos/faults/net_latency.py`

- [ ] **Step 2.1: Write failing tests**

Create `tests/test_fault_local_only.py`:

```python
"""Tests that all registered faults expose the local_only attribute correctly."""

from __future__ import annotations

import pytest

from kvmchaos.faults import FAULTS
from kvmchaos.faults.net_latency import NetLatencyFault
from kvmchaos.faults.vm_freeze import VmFreezeFault
from kvmchaos.faults.vm_kill import VmKillFault
from kvmchaos.faults.vm_pause import VmPauseFault
from kvmchaos.faults.vm_starve import VmStarveFault


@pytest.mark.parametrize("name,fault", list(FAULTS.items()))
def test_all_faults_have_local_only(name: str, fault: object) -> None:
    assert hasattr(fault, "local_only"), f"{name} missing local_only"
    assert isinstance(fault.local_only, bool)


def test_net_latency_is_local_only() -> None:
    assert NetLatencyFault.local_only is True


@pytest.mark.parametrize("cls", [VmPauseFault, VmKillFault, VmFreezeFault, VmStarveFault])
def test_vm_faults_are_not_local_only(cls: type) -> None:
    assert cls.local_only is False
```

- [ ] **Step 2.2: Run tests and confirm they fail**

```bash
uv run pytest tests/test_fault_local_only.py -v
```

Expected: `AttributeError: type object 'VmPauseFault' has no attribute 'local_only'`

- [ ] **Step 2.3: Add `local_only` to the `Fault` Protocol**

In `src/kvmchaos/faults/base.py`, add after the `destructive` field:

```python
    local_only: ClassVar[bool]
    """True if the fault requires local execution (subprocess on the KVM host)."""
```

The full updated Protocol class body (replace the existing class definition):

```python
class Fault(Protocol):
    """Structural interface that all fault implementations must satisfy.

    Fault classes are stateless — all state lives on the `virDomain`.
    The registry holds one singleton instance per fault class.
    """

    name: ClassVar[str]
    """Dotted identifier used as the registry key, e.g. ``'vm.pause'``."""

    description: ClassVar[str]
    """One-line human summary shown by ``kvmchaos list-faults``."""

    destructive: ClassVar[bool]
    """True if the fault kills or otherwise disrupts running guest state."""

    local_only: ClassVar[bool]
    """True if the fault requires local execution (subprocess on the KVM host)."""

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply the fault to the domain.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: On libvirt API failure.
        """
        ...

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that the fault is in effect.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If the domain is not in the expected fault state.
            libvirt.libvirtError: On libvirt API failure.
        """
        ...

    def revert(self, domain: libvirt.virDomain) -> None:
        """Undo the fault and restore the domain to its pre-inject state.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: On libvirt API failure.
        """
        ...
```

- [ ] **Step 2.4: Add `local_only = False` to VM fault classes**

In each of these four files, add `local_only: ClassVar[bool] = False` immediately after the `destructive` line:

**`src/kvmchaos/faults/vm_pause.py`** — class body becomes:
```python
    name: ClassVar[str] = "vm.pause"
    description: ClassVar[str] = "Suspend vCPUs; RAM preserved. Guest clock drifts."
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = False
```

**`src/kvmchaos/faults/vm_kill.py`** — add the same line after `destructive`.

**`src/kvmchaos/faults/vm_freeze.py`** — add the same line after `destructive`.

**`src/kvmchaos/faults/vm_starve.py`** — add the same line after `destructive`.

- [ ] **Step 2.5: Add `local_only = True` to `NetLatencyFault`**

In `src/kvmchaos/faults/net_latency.py`, add after `destructive`:

```python
    local_only: ClassVar[bool] = True
```

The class attribute block becomes:
```python
    name: ClassVar[str] = "net.latency"
    description: ClassVar[str] = f"Add {_DELAY_MS}ms one-way latency to first vNIC via tc netem."
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True
```

- [ ] **Step 2.6: Run tests and confirm they pass**

```bash
uv run pytest tests/test_fault_local_only.py -v
```

Expected: 9 tests pass.

- [ ] **Step 2.7: Run full suite to confirm no regressions**

```bash
uv run pytest -q
```

Expected: all existing tests pass.

- [ ] **Step 2.8: Commit**

```bash
git add src/kvmchaos/faults/base.py \
        src/kvmchaos/faults/vm_pause.py \
        src/kvmchaos/faults/vm_kill.py \
        src/kvmchaos/faults/vm_freeze.py \
        src/kvmchaos/faults/vm_starve.py \
        src/kvmchaos/faults/net_latency.py \
        tests/test_fault_local_only.py
git commit -m "feat: add local_only attribute to Fault Protocol and all fault classes"
```

---

## Task 3: `_is_remote` helper and remote guard in CLI

> Depends on Task 2 (needs `local_only` on faults). Must complete before Task 4.

**Files:**
- Create: `tests/test_remote_guard.py`
- Modify: `src/kvmchaos/cli.py`

- [ ] **Step 3.1: Write failing tests**

Create `tests/test_remote_guard.py`:

```python
"""Tests for _is_remote helper and the net.latency remote guard."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from kvmchaos.cli import _is_remote, app

runner = CliRunner()


class TestIsRemote:
    @pytest.mark.parametrize(
        "uri",
        [
            "qemu:///system",
            "qemu://localhost/system",
            "qemu://127.0.0.1/system",
            "qemu://[::1]/system",
        ],
    )
    def test_local_uris(self, uri: str) -> None:
        assert _is_remote(uri) is False

    @pytest.mark.parametrize(
        "uri",
        [
            "qemu+ssh://192.168.1.10/system",
            "qemu+ssh://hypervisor.local/system",
            "qemu+ssh://root@kvm-host/system",
        ],
    )
    def test_remote_uris(self, uri: str) -> None:
        assert _is_remote(uri) is True


class TestRemoteGuard:
    def test_local_only_fault_with_remote_uri_exits_2(self) -> None:
        result = runner.invoke(
            app,
            [
                "--connect",
                "qemu+ssh://192.168.1.10/system",
                "inject",
                "--yes",
                "net.latency",
                "server1",
            ],
        )
        assert result.exit_code == 2
        assert "requires local execution" in result.output

    def test_local_only_fault_with_local_uri_is_not_blocked(self) -> None:
        result = runner.invoke(
            app,
            ["--connect", "test:///default", "inject", "--yes", "--dry-run", "net.latency", "test"],
        )
        assert "requires local execution" not in result.output

    def test_non_local_only_fault_with_remote_uri_not_blocked(self) -> None:
        # vm.pause is not local_only — guard must not trigger.
        # Connection will fail (can't reach 192.168.1.10 in tests) but
        # the error must not be the guard message.
        result = runner.invoke(
            app,
            [
                "--connect",
                "qemu+ssh://192.168.1.10/system",
                "inject",
                "--yes",
                "vm.pause",
                "server1",
            ],
        )
        assert "requires local execution" not in result.output
```

- [ ] **Step 3.2: Run tests and confirm they fail**

```bash
uv run pytest tests/test_remote_guard.py -v
```

Expected: `ImportError: cannot import name '_is_remote' from 'kvmchaos.cli'`

- [ ] **Step 3.3: Add imports to `cli.py`**

Add these two imports at the top of `src/kvmchaos/cli.py`, inserting them in the stdlib block:

```python
import urllib.parse
```

Change the `libvirt_conn` import line from:
```python
from kvmchaos.libvirt_conn import connect
```
to:
```python
from kvmchaos.libvirt_conn import connect, resolve_uri
```

- [ ] **Step 3.4: Add `_is_remote` function to `cli.py`**

Add this function after `_state_name` and before `inject_cmd`:

```python
def _is_remote(uri: str) -> bool:
    """Return True if the URI refers to a non-local libvirt host.

    A URI with an empty hostname (e.g. ``qemu:///system``) is a local Unix
    socket. ``localhost``, ``127.0.0.1``, and ``::1`` are also treated as local.

    Args:
        uri: Resolved libvirt connection URI.

    Returns:
        True if the hostname is non-empty and not a localhost alias.
    """
    host = urllib.parse.urlparse(uri).hostname or ""
    return host not in ("", "localhost", "127.0.0.1", "::1")
```

- [ ] **Step 3.5: Update `inject_cmd` to resolve URI and add the guard**

In `inject_cmd`, replace:

```python
    uri = ctx.obj.get(_CTX_KEY) if ctx.obj else None
    with connect(uri) as conn:
```

with:

```python
    raw_uri = ctx.obj.get(_CTX_KEY) if ctx.obj else None
    resolved_uri = resolve_uri(raw_uri)

    if fault.local_only and _is_remote(resolved_uri):
        typer.echo(
            f"{fault_name} requires local execution — run kvmchaos directly on the KVM host.",
            err=True,
        )
        raise typer.Exit(code=2)

    with connect(resolved_uri) as conn:
```

- [ ] **Step 3.6: Run tests and confirm they pass**

```bash
uv run pytest tests/test_remote_guard.py -v
```

Expected: 7 tests pass.

- [ ] **Step 3.7: Run full suite to confirm no regressions**

```bash
uv run pytest -q
```

Expected: all existing tests pass.

- [ ] **Step 3.8: Commit**

```bash
git add src/kvmchaos/cli.py tests/test_remote_guard.py
git commit -m "feat: add _is_remote guard — block net.latency against remote libvirt URIs"
```

---

## Task 4: `_run_step` returns dict and `inject_cmd` writes run records

> Depends on Tasks 1 and 3.

**Files:**
- Modify: `src/kvmchaos/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 4.1: Write failing integration tests**

Add a new class `TestRunRecord` to `tests/test_cli.py` (after the existing `TestInject` class):

```python
class TestRunRecord:
    def test_record_written_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(
            app,
            [
                "--connect", "test:///default",
                "inject", "--yes", "--duration", "0",
                "vm.pause", "test",
            ],
        )
        assert result.exit_code == 0
        runs_dir = tmp_path / "kvmchaos" / "runs"
        records = list(runs_dir.glob("*.json"))
        assert len(records) == 1
        data = json.loads(records[0].read_text())
        assert data["fault"] == "vm.pause"
        assert data["vm"] == "test"
        assert data["outcome"] == "success"
        assert data["dry_run"] is False
        assert [s["action"] for s in data["steps"]] == ["inject", "verify", "revert"]

    def test_record_written_for_dry_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(
            app,
            [
                "--connect", "test:///default",
                "inject", "--yes", "--dry-run",
                "vm.pause", "test",
            ],
        )
        assert result.exit_code == 0
        runs_dir = tmp_path / "kvmchaos" / "runs"
        records = list(runs_dir.glob("*.json"))
        assert len(records) == 1
        data = json.loads(records[0].read_text())
        assert data["dry_run"] is True
        assert all(s["result"] == "skipped" for s in data["steps"])
        assert data["outcome"] == "success"

    def test_record_path_printed_to_stdout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(
            app,
            [
                "--connect", "test:///default",
                "inject", "--yes", "--duration", "0",
                "vm.pause", "test",
            ],
        )
        assert result.exit_code == 0
        assert "Run record:" in result.stdout
```

Also add `import pytest` to the imports in `tests/test_cli.py` (it currently doesn't import pytest directly — add it):

```python
import pytest
```

- [ ] **Step 4.2: Run failing tests**

```bash
uv run pytest tests/test_cli.py::TestRunRecord -v
```

Expected: `AssertionError` — no `runs` directory exists yet.

- [ ] **Step 4.3: Add new imports to `cli.py`**

Add to the stdlib import block at the top of `src/kvmchaos/cli.py`:

```python
from datetime import UTC, datetime
```

Add to the kvmchaos imports:

```python
from kvmchaos.runrecord import default_runs_dir, write_run_record
```

- [ ] **Step 4.4: Replace `_run_step` with the new dict-returning version**

Replace the entire `_run_step` function in `src/kvmchaos/cli.py` with:

```python
def _run_step(
    func: Callable[[libvirt.virDomain], None],
    domain: libvirt.virDomain,
    *,
    action: str,
    fault_name: str,
    vm: str,
    dry_run: bool = False,
) -> dict[str, object]:
    """Execute one fault step (inject, verify, or revert) and log the outcome.

    Args:
        func: Callable to invoke — one of ``fault.inject``, ``.verify``, ``.revert``.
        domain: Live libvirt domain handle.
        action: Event label (``'inject'``, ``'verify'``, or ``'revert'``).
        fault_name: Fault registry key, included in the log event.
        vm: VM name, included in the log event.
        dry_run: If True, print a plan line and return without calling func or logging.

    Returns:
        Dict with ``action``, ``result`` (``'ok'``, ``'fail'``, or ``'skipped'``),
        ``duration_ms``, and optional ``error``.
    """
    if dry_run:
        typer.echo(f"[dry-run] would: {action} {fault_name} on {vm}")
        return {"action": action, "result": "skipped", "duration_ms": 0}
    t0 = time.monotonic()
    try:
        func(domain)
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        log_event(
            action=action,
            fault=fault_name,
            vm=vm,
            result="fail",
            duration_ms=duration_ms,
            error=str(exc),
        )
        typer.echo(f"{action} error: {exc}", err=True)
        return {"action": action, "result": "fail", "duration_ms": duration_ms, "error": str(exc)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(action=action, fault=fault_name, vm=vm, result="ok", duration_ms=duration_ms)
    return {"action": action, "result": "ok", "duration_ms": duration_ms}
```

- [ ] **Step 4.5: Add `_write_and_print_record` helper to `cli.py`**

Add this function immediately after `_run_step`:

```python
def _write_and_print_record(
    fault_name: str,
    vm: str,
    uri: str,
    dry_run: bool,
    started_at: datetime,
    ended_at: datetime,
    steps: list[dict[str, object]],
) -> None:
    """Build the run record dict, write it to disk, and print its path.

    Args:
        fault_name: Name of the fault that was injected.
        vm: Target VM name.
        uri: Resolved libvirt URI used for the run.
        dry_run: True if the run was a dry-run.
        started_at: UTC datetime when inject_cmd began executing steps.
        ended_at: UTC datetime when the final step completed.
        steps: List of step result dicts from ``_run_step``.
    """
    outcome = "success" if all(s["result"] in ("ok", "skipped") for s in steps) else "fail"
    record: dict[str, object] = {
        "started_at": started_at.isoformat(timespec="seconds"),
        "ended_at": ended_at.isoformat(timespec="seconds"),
        "fault": fault_name,
        "vm": vm,
        "uri": uri,
        "dry_run": dry_run,
        "duration_s": int((ended_at - started_at).total_seconds()),
        "outcome": outcome,
        "steps": steps,
    }
    path = write_run_record(record, default_runs_dir())
    typer.echo(f"Run record: {path}")
```

- [ ] **Step 4.6: Update `inject_cmd` to collect steps and write the record**

Replace the body of `inject_cmd` (after the fault lookup and guard — from `started_at` through the end of the `with` block) with:

```python
    started_at = datetime.now(UTC)
    steps: list[dict[str, object]] = []

    with connect(resolved_uri) as conn:
        try:
            domain = conn.lookupByName(vm)
        except libvirt.libvirtError as exc:
            typer.echo(f"VM '{vm}' not found: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        if not dry_run:
            label = "DESTRUCTIVE" if fault.destructive else "reversible"
            prompt = f"About to inject '{fault_name}' on VM '{vm}' ({label}). Continue?"
            if not confirm(prompt, assume_yes=assume_yes):
                typer.echo("Aborted.")
                raise typer.Exit(code=1)

        inject_step = _run_step(
            fault.inject, domain, action="inject", fault_name=fault_name, vm=vm, dry_run=dry_run
        )
        steps.append(inject_step)
        if inject_step["result"] == "fail":
            ended_at = datetime.now(UTC)
            _write_and_print_record(fault_name, vm, resolved_uri, dry_run, started_at, ended_at, steps)
            raise typer.Exit(code=1)

        verify_step = _run_step(
            fault.verify, domain, action="verify", fault_name=fault_name, vm=vm, dry_run=dry_run
        )
        steps.append(verify_step)
        if verify_step["result"] == "fail":
            revert_step = _run_step(
                fault.revert,
                domain,
                action="revert",
                fault_name=fault_name,
                vm=vm,
                dry_run=dry_run,
            )
            steps.append(revert_step)
            ended_at = datetime.now(UTC)
            _write_and_print_record(fault_name, vm, resolved_uri, dry_run, started_at, ended_at, steps)
            raise typer.Exit(code=1)

        if dry_run:
            typer.echo(f"[dry-run] would: hold {fault_name} on {vm} for {duration}s")
        elif duration > 0:
            typer.echo(f"Holding '{fault_name}' on '{vm}' for {duration}s …")
            time.sleep(duration)

        revert_step = _run_step(
            fault.revert, domain, action="revert", fault_name=fault_name, vm=vm, dry_run=dry_run
        )
        steps.append(revert_step)

        ended_at = datetime.now(UTC)
        _write_and_print_record(fault_name, vm, resolved_uri, dry_run, started_at, ended_at, steps)
```

The complete `inject_cmd` signature and preamble (unchanged from Task 3, shown for context):

```python
@app.command("inject")
def inject_cmd(
    ctx: typer.Context,
    fault_name: str = typer.Argument(..., metavar="FAULT", help="Fault name. See `list-faults`."),
    vm: str = typer.Argument(..., metavar="VM", help="Target VM name."),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Print plan without making changes."
    ),
    duration: int = typer.Option(
        20, "--duration", "-d", help="Seconds to hold the fault before reverting.", min=0
    ),
) -> None:
    """Inject a fault into a VM, verify it took effect, then revert.

    Exits 0 on full success, 1 on runtime failure, 2 on usage error.

    Args:
        ctx: Typer context; carries the ``--connect`` URI.
        fault_name: Name of the fault to inject (see ``list-faults``).
        vm: Name of the target libvirt domain.
        assume_yes: If True, skip the confirmation prompt.
        dry_run: If True, validate args and print plan without touching libvirt state.
        duration: Seconds to hold the fault before reverting.
    """
    configure_logging()

    if fault_name not in FAULTS:
        typer.echo(
            f"Unknown fault: {fault_name!r}. Known faults: {', '.join(sorted(FAULTS))}",
            err=True,
        )
        raise typer.Exit(code=2)
    fault = FAULTS[fault_name]

    raw_uri = ctx.obj.get(_CTX_KEY) if ctx.obj else None
    resolved_uri = resolve_uri(raw_uri)

    if fault.local_only and _is_remote(resolved_uri):
        typer.echo(
            f"{fault_name} requires local execution — run kvmchaos directly on the KVM host.",
            err=True,
        )
        raise typer.Exit(code=2)

    # ... started_at, steps, with connect(resolved_uri) ... (from Step 4.6)
```

- [ ] **Step 4.7: Run new tests and confirm they pass**

```bash
uv run pytest tests/test_cli.py::TestRunRecord -v
```

Expected: 3 tests pass.

- [ ] **Step 4.8: Run full suite**

```bash
uv run pytest -q
```

Expected: all tests pass, coverage ≥85%.

- [ ] **Step 4.9: Run linters**

```bash
uv run ruff check && uv run ruff format --check
```

Expected: no errors.

- [ ] **Step 4.10: Commit**

```bash
git add src/kvmchaos/cli.py tests/test_cli.py
git commit -m "feat: write per-run JSON record after every inject invocation"
```

---

## Task 5: Lab checklist in PLAN.md and version bump

**Files:**
- Modify: `PLAN.md`

- [ ] **Step 5.1: Add v0.3 acceptance and lab checklist to `PLAN.md`**

Add after the v0.2 acceptance section:

```markdown
## Acceptance (v0.3)

- [ ] `kvmchaos inject vm.pause <vm> --yes --duration 0` writes a `.json` file to `~/.local/state/kvmchaos/runs/`
- [ ] `kvmchaos inject vm.pause <vm> --dry-run` writes a record with `dry_run: true` and all steps `skipped`
- [ ] `kvmchaos inject net.latency <vm> --connect qemu+ssh://<remote>/system` exits 2 with local-only message
- [ ] `kvmchaos inject vm.pause <vm> --connect qemu+ssh://localhost/system --yes --duration 0` completes successfully (requires `ssh-copy-id localhost`)
- [ ] `pytest` passes with coverage ≥85%
- [ ] `ruff check`, `ruff format --check` clean

## Lab Validation (v0.3)

After automated tests pass, manually test against the lab environment:
**Host:** Fedora 43 KVM · **Guest:** RHEL 9.7 VM

Pre-requisite: `ssh-copy-id localhost` on the KVM host (authorizes key for loopback SSH).

- [ ] `kvmchaos --connect qemu+ssh://localhost/system list-vms` shows the RHEL 9.7 VM
- [ ] `kvmchaos --connect qemu+ssh://localhost/system inject vm.pause server1 --yes --duration 5` completes; run record written to `~/.local/state/kvmchaos/runs/`
- [ ] `cat` the run record — JSON parses, `outcome: success`, 3 steps all `ok`
- [ ] `kvmchaos --connect qemu+ssh://localhost/system inject net.latency server1 --yes` exits 2 with `requires local execution` message
- [ ] `kvmchaos inject vm.pause server1 --yes --dry-run` writes a record with `dry_run: true`
```

- [ ] **Step 5.2: Commit PLAN.md**

```bash
git add PLAN.md
git commit -m "docs: add v0.3 acceptance criteria and lab validation checklist"
```
