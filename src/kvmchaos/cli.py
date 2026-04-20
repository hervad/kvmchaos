"""Typer CLI entry point for kvmchaos.

Provides: ``--version``, ``list-vms``, ``list-faults``.
The ``inject`` command is defined in Task 10 and appended to this module.

The CLI is a thin orchestration layer: it resolves a libvirt URI, looks
up a fault in the registry, prompts for confirmation, and drives the
inject/verify/revert sequence. This module contains only the scaffolding;
fault logic lives in `kvmchaos.faults`.
"""

from __future__ import annotations

import typer

from kvmchaos import __version__
from kvmchaos.faults import FAULTS
from kvmchaos.libvirt_conn import connect

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
    """Root callback — stashes --connect URI on the Typer context."""
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


def _state_name(state: int) -> str:
    """Convert a libvirt domain state integer to a human-readable label.

    Args:
        state: Integer domain state from `virDomain.state()[0]`.

    Returns:
        A lowercase string label, or ``'stateN'`` for unknown values.
    """
    return _STATE_NAMES.get(state, f"state{state}")
