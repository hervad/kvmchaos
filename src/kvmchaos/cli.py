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

import libvirt
import typer

from kvmchaos import __version__
from kvmchaos.eventlog import configure_logging, log_event
from kvmchaos.faults import FAULTS
from kvmchaos.libvirt_conn import connect
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
    for name, fault in FAULTS.items():
        marker = "destructive" if fault.destructive else "safe"
        typer.echo(f"{name}\t[{marker}]\t{fault.description}")


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


@app.command("inject")
def inject_cmd(
    ctx: typer.Context,
    fault_name: str = typer.Argument(..., metavar="FAULT", help="Fault name. See `list-faults`."),
    vm: str = typer.Argument(..., metavar="VM", help="Target VM name."),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Inject a fault into a VM, verify it took effect, then revert.

    Exits 0 on full success, 1 on runtime failure, 2 on usage error.

    Args:
        ctx: Typer context; carries the ``--connect`` URI.
        fault_name: Name of the fault to inject (see ``list-faults``).
        vm: Name of the target libvirt domain.
        assume_yes: If True, skip the confirmation prompt.
    """
    configure_logging()

    if fault_name not in FAULTS:
        typer.echo(
            f"Unknown fault: {fault_name!r}. Known faults: {', '.join(sorted(FAULTS))}",
            err=True,
        )
        raise typer.Exit(code=2)
    fault = FAULTS[fault_name]

    uri = ctx.obj.get(_CTX_KEY) if ctx.obj else None
    with connect(uri) as conn:
        try:
            domain = conn.lookupByName(vm)
        except libvirt.libvirtError as exc:
            typer.echo(f"VM '{vm}' not found: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        label = "DESTRUCTIVE" if fault.destructive else "reversible"
        prompt = f"About to inject '{fault_name}' on VM '{vm}' ({label}). Continue?"
        if not confirm(prompt, assume_yes=assume_yes):
            typer.echo("Aborted.")
            raise typer.Exit(code=1)

        _run_step(fault.inject, domain, action="inject", fault_name=fault_name, vm=vm)

        try:
            _run_step(fault.verify, domain, action="verify", fault_name=fault_name, vm=vm)
        except Exception:
            # Verify failed — attempt revert to avoid leaving the VM broken,
            # but don't let a revert failure mask the verify failure.
            _run_step(
                fault.revert,
                domain,
                action="revert",
                fault_name=fault_name,
                vm=vm,
                swallow=True,
            )
            raise typer.Exit(code=1) from None

        _run_step(fault.revert, domain, action="revert", fault_name=fault_name, vm=vm)


def _run_step(
    func,
    domain: libvirt.virDomain,
    *,
    action: str,
    fault_name: str,
    vm: str,
    swallow: bool = False,
) -> None:
    """Execute one fault step (inject, verify, or revert) and log the outcome.

    Args:
        func: Callable to invoke — one of ``fault.inject``, ``.verify``, ``.revert``.
        domain: Live libvirt domain handle.
        action: Event label for the log (``'inject'``, ``'verify'``, ``'revert'``).
        fault_name: Fault registry key, included in the log event.
        vm: VM name, included in the log event.
        swallow: If True, log the error and return instead of re-raising.
    """
    t0 = time.monotonic()
    try:
        func(domain)
    except Exception as exc:
        log_event(
            action=action,
            fault=fault_name,
            vm=vm,
            result="fail",
            duration_ms=int((time.monotonic() - t0) * 1000),
            error=str(exc),
        )
        if swallow:
            typer.echo(f"{action} error (best-effort): {exc}", err=True)
            return
        typer.echo(f"{action} failed: {exc}", err=True)
        raise
    log_event(
        action=action,
        fault=fault_name,
        vm=vm,
        result="ok",
        duration_ms=int((time.monotonic() - t0) * 1000),
    )


def _state_name(state: int) -> str:
    """Convert a libvirt domain state integer to a human-readable label.

    Args:
        state: Integer domain state from `virDomain.state()[0]`.

    Returns:
        A lowercase string label, or ``'stateN'`` for unknown values.
    """
    return _STATE_NAMES.get(state, f"state{state}")
