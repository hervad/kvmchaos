"""Typer CLI entry point for kvmchaos.

Provides: ``--version``, ``list-vms``, ``list-faults``.
The ``inject`` command is defined in Task 10 and appended to this module.

The CLI is a thin orchestration layer: it resolves a libvirt URI, looks
up a fault in the registry, prompts for confirmation, and drives the
inject/verify/revert sequence. This module contains only the scaffolding;
fault logic lives in `kvmchaos.faults`.
"""

from __future__ import annotations

import time
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime

import libvirt
import typer

from kvmchaos import __version__
from kvmchaos.eventlog import configure_logging, log_event
from kvmchaos.faults import FAULTS
from kvmchaos.faults.disk_latency import DiskLatencyFault
from kvmchaos.libvirt_conn import connect, resolve_uri
from kvmchaos.runrecord import default_runs_dir, write_run_record
from kvmchaos.safety import confirm

app = typer.Typer(
    help="Agent-less chaos engineering for KVM/libvirt VMs.",
    no_args_is_help=True,
    add_completion=False,
)

# Shared state passed from the root callback to subcommands via Context.obj.
_CTX_KEY = "connect_uri"


def _version_callback(value: bool) -> None:
    """Print version string and exit when --version is passed.

    Args:
        value: True when the flag is present, False otherwise.
    """
    if value:
        typer.echo(f"kvmchaos {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    connect_uri: str | None = typer.Option(
        None,
        "--connect",
        help="libvirt URI (overrides LIBVIRT_DEFAULT_URI).",
    ),
) -> None:
    """Root callback — stashes --connect URI on the Typer context.

    Args:
        ctx: Typer context object; used to pass the connect URI to subcommands.
        version: If True, print version and exit (handled by eager callback).
        connect_uri: libvirt URI override. Stored on ctx.obj for subcommands.
    """
    ctx.ensure_object(dict)
    ctx.obj[_CTX_KEY] = connect_uri


@app.command("list-vms")
def list_vms(ctx: typer.Context) -> None:
    """List all domains on the connected libvirt URI."""
    uri = ctx.obj.get(_CTX_KEY) if ctx.obj else None
    with connect(uri) as conn:
        for domain in conn.listAllDomains():
            state, _ = domain.state()
            typer.echo(f"{domain.name()}\t{_state_name(state)}")


@app.command("list-faults")
def list_faults() -> None:
    """List registered faults with descriptions."""
    col_name = max(len(n) for n in FAULTS) if FAULTS else 0
    for name, fault in FAULTS.items():
        marker = "destructive" if fault.destructive else "safe"
        typer.echo(f"{name:<{col_name}}  [{marker:<11}]  {fault.description}")


# Map libvirt domain state integers to human-readable strings.
# Values from libvirt.h virDomainState enum.
_STATE_NAMES: dict[int, str] = {
    0: "nostate",
    1: "running",
    2: "blocked",
    3: "paused",
    4: "shutdown",
    5: "shutoff",
    6: "crashed",
    7: "suspended",
}


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
    bandwidth: int = typer.Option(
        1,
        "--bandwidth",
        "-b",
        help="Disk throttle limit in MB/s (disk.latency only).",
        min=1,
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
        bandwidth: Disk I/O throttle in MB/s, used only by disk.latency.
    """
    configure_logging()

    if fault_name not in FAULTS:
        typer.echo(
            f"Unknown fault: {fault_name!r}. Known faults: {', '.join(sorted(FAULTS))}",
            err=True,
        )
        raise typer.Exit(code=2)
    fault = FAULTS[fault_name]
    if fault_name == "disk.latency":
        fault = DiskLatencyFault(bandwidth_bps=bandwidth * 1_000_000)

    raw_uri = ctx.obj.get(_CTX_KEY) if ctx.obj else None
    resolved_uri = resolve_uri(raw_uri)

    if fault.local_only and _is_remote(resolved_uri):
        typer.echo(
            f"{fault_name} requires local execution — run kvmchaos directly on the KVM host.",
            err=True,
        )
        raise typer.Exit(code=2)

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

        started_at = datetime.now(UTC)
        steps: list[dict[str, object]] = []

        inject_step = _run_step(
            fault.inject, domain, action="inject", fault_name=fault_name, vm=vm, dry_run=dry_run
        )
        steps.append(inject_step)
        if inject_step["result"] == "fail":
            ended_at = datetime.now(UTC)
            _write_and_print_record(
                fault_name, vm, resolved_uri, dry_run, started_at, ended_at, steps
            )
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
            _write_and_print_record(
                fault_name, vm, resolved_uri, dry_run, started_at, ended_at, steps
            )
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


def _state_name(state: int) -> str:
    """Convert a libvirt domain state integer to a human-readable label.

    Args:
        state: Integer domain state from `virDomain.state()[0]`.

    Returns:
        A lowercase string label, or ``'stateN'`` for unknown values.
    """
    return _STATE_NAMES.get(state, f"state{state}")
