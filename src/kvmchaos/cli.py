"""Typer CLI entry point for kvmchaos.

Provides: ``--version``, ``list-vms``, ``list-faults``.
The ``inject`` command is defined in Task 10 and appended to this module.

The CLI is a thin orchestration layer: it resolves a libvirt URI, looks
up a fault in the registry, prompts for confirmation, and drives the
inject/verify/revert sequence. This module contains only the scaffolding;
fault logic lives in `kvmchaos.faults`.
"""

from __future__ import annotations

import json
import signal
import time
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import libvirt
import typer

from kvmchaos import __version__
from kvmchaos.config import load_config, rate_limit_violation
from kvmchaos.eventlog import configure_logging, log_event
from kvmchaos.experiment import Step, load_experiment
from kvmchaos.faults import FAULTS
from kvmchaos.faults.base import Fault
from kvmchaos.faults.clock_skew import ClockSkewFault
from kvmchaos.faults.disk_fill import DiskFillFault
from kvmchaos.faults.disk_latency import DiskLatencyFault
from kvmchaos.faults.net_bandwidth import NetBandwidthFault
from kvmchaos.faults.net_corrupt import NetCorruptFault
from kvmchaos.faults.net_packet_loss import NetPacketLossFault
from kvmchaos.libvirt_conn import connect, resolve_uri
from kvmchaos.observability import emit as _obs_emit
from kvmchaos.observability import events as obs_events
from kvmchaos.observability import logging as obs_logging
from kvmchaos.observability import set_notifier as _obs_set_notifier
from kvmchaos.observability.notifier import Notifier
from kvmchaos.report import load_records, render_html
from kvmchaos.runrecord import (
    default_runs_dir,
    filter_records,
    load_record,
    resolve_id,
    write_run_record,
)
from kvmchaos.safety import confirm

app = typer.Typer(
    help="Agent-less chaos engineering for KVM/libvirt VMs.",
    no_args_is_help=True,
    add_completion=False,
)

# Shared state passed from the root callback to subcommands via Context.obj.
_CTX_KEY = "connect_uri"

_DEFAULT_REPORT_PATH = Path("kvmchaos-report.html")


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
    obs_logging.configure_stderr_logging(verbose=False)
    import sys as _sys

    _emit_mod = _sys.modules.get("kvmchaos.observability.emit")
    if _emit_mod is not None and getattr(_emit_mod, "_NOTIFIER", None) is None:
        cfg = load_config(None)
        _obs_set_notifier(Notifier(cfg.notifier))


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


@app.command("doctor")
def doctor_cmd(ctx: typer.Context) -> None:
    """Diagnose the most common first-run environment problems.

    Checks (in order):

    * ``tc`` binary is on PATH (net.* faults)
    * ``cgroup2`` is mounted at ``/sys/fs/cgroup`` (disk.latency)
    * user is in the ``libvirt`` group (required for unauthenticated local conn)
    * libvirtd is reachable on the resolved URI
    * the runs directory is writable

    Exits 0 if all checks pass, 1 if any warn, 2 if any fail.
    """
    import grp
    import os
    import pwd
    import shutil

    from kvmchaos.runrecord import default_runs_dir

    uri = ctx.obj.get(_CTX_KEY) if ctx.obj else None
    resolved = resolve_uri(uri)
    fail = False
    warn = False

    def check(label: str, ok: bool, hint: str = "") -> None:
        nonlocal fail
        marker = "ok  " if ok else "FAIL"
        typer.echo(f"  [{marker}] {label}")
        if not ok:
            fail = True
            if hint:
                typer.echo(f"         hint: {hint}")

    typer.echo(f"kvmchaos doctor (uri: {resolved})")
    check(
        "tc binary on PATH",
        shutil.which("tc") is not None,
        "install iproute2 (Fedora/RHEL: `sudo dnf install iproute`)",
    )
    check(
        "cgroup v2 mounted at /sys/fs/cgroup",
        Path("/sys/fs/cgroup/cgroup.controllers").is_file(),
        "RHEL 8 defaults to cgroup v1; disk.latency requires v2",
    )

    # libvirt group membership (skip when we're root — root doesn't need the group)
    if os.geteuid() != 0:
        try:
            libvirt_gid = grp.getgrnam("libvirt").gr_gid
            user_gids = [
                g.gr_gid for g in grp.getgrall() if pwd.getpwuid(os.getuid()).pw_name in g.gr_mem
            ]
            in_group = libvirt_gid in user_gids or libvirt_gid in os.getgroups()
            check(
                "user is in libvirt group",
                in_group,
                "run: sudo usermod -aG libvirt $USER && re-login",
            )
        except KeyError:
            typer.echo("  [warn] libvirt group not found on system")
            warn = True

    # libvirtd reachability
    try:
        with connect(resolved) as conn:
            conn.getHostname()
        check("libvirtd reachable", ok=True)
    except (OSError, libvirt.libvirtError) as exc:
        check("libvirtd reachable", ok=False, hint=f"{exc}")

    # Runs dir writable
    runs_dir = default_runs_dir()
    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
        probe = runs_dir / ".doctor-probe"
        probe.write_text("")
        probe.unlink()
        check(f"runs dir writable ({runs_dir})", ok=True)
    except OSError as exc:
        check(f"runs dir writable ({runs_dir})", ok=False, hint=str(exc))

    if fail:
        raise typer.Exit(code=2)
    if warn:
        raise typer.Exit(code=1)


@app.command("abort-all")
def abort_all_cmd(
    ctx: typer.Context,
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Revert all active ``net.*`` faults on this host — emergency stop.

    Scans every running domain's first tap device and calls ``tc qdisc del root``
    on any that have an active netem qdisc. This is the most common stuck state
    (a failed revert leaves a VM unreachable).

    Does NOT revert disk.latency, vm.pause, vm.freeze, or clock.skew — those
    require per-fault metadata (the pre-inject value) to revert correctly.
    Run the original ``kvmchaos inject`` again with ``--duration 0`` to force
    a revert for those.

    Exits 0 if the scan completes (even with nothing to clean up), 1 if the
    user aborts.
    """
    import kvmchaos.tc as tc

    raw_uri = ctx.obj.get(_CTX_KEY) if ctx.obj else None
    resolved_uri = resolve_uri(raw_uri)

    cleared: list[tuple[str, str]] = []  # (vm_name, dev)
    with connect(resolved_uri) as conn:
        for domain in conn.listAllDomains():
            state, _ = domain.state()
            if state != libvirt.VIR_DOMAIN_RUNNING:
                continue
            try:
                dev = tc.tap_device(domain)
            except RuntimeError:
                continue  # no interface; nothing to revert
            if "netem" in tc.show_qdisc(dev):
                cleared.append((domain.name(), dev))

    if not cleared:
        typer.echo("No active net.* faults found.")
        return

    typer.echo("Active net.* faults to revert:")
    for name, dev in cleared:
        typer.echo(f"  {name} ({dev})")
    if not assume_yes:
        prompt = f"Revert {len(cleared)} active fault(s)? Continue?"
        if not confirm(prompt, assume_yes=False):
            typer.echo("Aborted.")
            raise typer.Exit(code=1)

    errors = 0
    for name, dev in cleared:
        try:
            tc.del_root_qdisc(dev)
            typer.echo(f"reverted: {name} ({dev})")
        except RuntimeError as exc:
            typer.echo(f"ERROR reverting {name} ({dev}): {exc}", err=True)
            errors += 1

    if errors:
        raise typer.Exit(code=1)


@app.command("report")
def report_cmd(
    output: Path = typer.Option(
        _DEFAULT_REPORT_PATH,
        "--output",
        "-o",
        help="Destination HTML file.",
    ),
    runs_dir: Path | None = typer.Option(
        None,
        "--runs-dir",
        help="Directory of run records. Defaults to $XDG_STATE_HOME/kvmchaos/runs.",
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        help="Keep runs with started_at ≥ this ISO date or datetime (assumes UTC if naive).",
    ),
    fault: str | None = typer.Option(None, "--fault", help="Only the named fault."),
    outcome: str | None = typer.Option(
        None, "--outcome", help="Only this outcome (success, fail, dry_run)."
    ),
    vm: str | None = typer.Option(None, "--vm", help="Only this VM name."),
) -> None:
    """Render a static HTML report of run records, optionally filtered.

    Args:
        output: Destination HTML file. Parent directories are created as needed.
        runs_dir: Runs directory. If omitted, ``default_runs_dir()`` is used.
        since: Optional lower bound on ``started_at``.
        fault: Optional exact fault name filter.
        outcome: Optional outcome filter (``success``/``fail``/``dry_run``).
        vm: Optional exact VM name filter.
    """
    target_runs = runs_dir if runs_dir is not None else default_runs_dir()
    records = filter_records(
        load_records(target_runs),
        since=_parse_since(since),
        fault=fault,
        outcome=outcome,
        vm=vm,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(records))
    typer.echo(f"Report: {output}")


def _parse_since(raw: str | None) -> datetime | None:
    """Parse a user-supplied ``--since`` argument into a UTC-aware datetime.

    Accepts any :func:`datetime.fromisoformat`-parseable string. A naive
    result (date-only or no timezone) is interpreted as UTC.

    Args:
        raw: Raw CLI argument, or ``None`` to disable the filter.

    Returns:
        Timezone-aware UTC datetime, or ``None`` when ``raw`` is ``None``.

    Raises:
        typer.BadParameter: If the string is not ISO 8601.
    """
    if raw is None:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise typer.BadParameter(f"--since must be ISO 8601 (got {raw!r})") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


runs_app = typer.Typer(
    help="Inspect saved run records.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(runs_app, name="runs")


@runs_app.command("list")
def runs_list_cmd(
    limit: int = typer.Option(20, "--limit", "-n", min=1, help="Max rows to print."),
    runs_dir: Path | None = typer.Option(
        None,
        "--runs-dir",
        help="Directory of run records. Defaults to $XDG_STATE_HOME/kvmchaos/runs.",
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        help="Keep runs with started_at ≥ this ISO date or datetime (assumes UTC if naive).",
    ),
    fault: str | None = typer.Option(None, "--fault", help="Only the named fault."),
    outcome: str | None = typer.Option(
        None, "--outcome", help="Only this outcome (success, fail, dry_run)."
    ),
    vm: str | None = typer.Option(None, "--vm", help="Only this VM name."),
) -> None:
    """List recent run records, newest first, with optional filters.

    Filters apply before ``--limit`` so the flag caps post-filter rows.

    Args:
        limit: Maximum number of rows to display (after filtering).
        runs_dir: Runs directory. If omitted, ``default_runs_dir()`` is used.
        since: Optional lower bound on ``started_at``.
        fault: Optional exact fault name filter.
        outcome: Optional outcome filter.
        vm: Optional exact VM name filter.
    """
    target = runs_dir if runs_dir is not None else default_runs_dir()
    records = load_records(target)
    records = filter_records(
        records, since=_parse_since(since), fault=fault, outcome=outcome, vm=vm
    )
    records = records[:limit]
    if not records:
        typer.echo("No runs.")
        return
    typer.echo(_runs_table(target, records))


@runs_app.command("show")
def runs_show_cmd(
    run_id: str = typer.Argument(..., metavar="ID", help="Run id or unambiguous prefix."),
    runs_dir: Path | None = typer.Option(
        None,
        "--runs-dir",
        help="Directory of run records. Defaults to $XDG_STATE_HOME/kvmchaos/runs.",
    ),
) -> None:
    """Print one run record as formatted JSON.

    Args:
        run_id: Full record stem or unambiguous prefix.
        runs_dir: Runs directory. If omitted, ``default_runs_dir()`` is used.
    """
    target = runs_dir if runs_dir is not None else default_runs_dir()
    try:
        path = resolve_id(target, run_id)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(load_record(path), indent=2))


def _runs_table(runs_dir: Path, records: list[dict[str, object]]) -> str:
    """Format a list of records as a plain-text table.

    Args:
        runs_dir: Directory the records came from (used to derive each ``id``
            as the filename stem).
        records: Pre-sorted records, newest first.

    Returns:
        A newline-separated table, header first.
    """
    columns = ("id", "started_at", "fault", "vm", "outcome", "duration_s")
    rows = [columns]
    for rec in records:
        rows.append(
            (
                _record_id(runs_dir, rec),
                str(rec.get("started_at", "")),
                str(rec.get("fault", "")),
                str(rec.get("vm", "")),
                str(rec.get("outcome", "")),
                str(rec.get("duration_s", "")),
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(columns))]
    return "\n".join("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows)


def _record_id(runs_dir: Path, record: dict[str, object]) -> str:
    """Derive a record's on-disk id from its fields.

    Mirrors the filename scheme in :func:`kvmchaos.runrecord.write_run_record`
    so callers can resolve the id back to a file without a second stat.
    """
    raw_ts = record.get("started_at", "")
    try:
        dt = datetime.fromisoformat(str(raw_ts)).astimezone(UTC)
        compact = dt.strftime("%Y%m%dT%H%M%SZ")
    except ValueError, TypeError:
        compact = str(raw_ts)
    fault_slug = str(record.get("fault", "")).replace(".", "-")
    return f"{compact}-{fault_slug}-{record.get('vm', '')}"


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


_FAULT_BUILDERS: dict[str, Callable[..., Fault]] = {
    "disk.latency": lambda bandwidth, **_: DiskLatencyFault(bandwidth_bps=bandwidth * 1_000_000),
    "disk.fill": lambda size, **_: DiskFillFault(fill_bytes=size * 1024 * 1024),
    "net.packet-loss": lambda loss, **_: NetPacketLossFault(loss_percent=loss),
    "net.bandwidth": lambda rate, **_: NetBandwidthFault(rate_kbps=rate),
    "net.corrupt": lambda corrupt, **_: NetCorruptFault(corrupt_percent=corrupt),
    "clock.skew": lambda skew, **_: ClockSkewFault(skew_seconds=skew),
}


def _build_fault(fault_name: str, **params: int) -> Fault:
    """Construct a fault instance, applying CLI params for parameterised faults.

    Faults without tunable parameters (e.g. ``vm.pause``) return the shared
    registry singleton. Parameterised faults are rebuilt from ``params`` via
    :data:`_FAULT_BUILDERS`.

    Args:
        fault_name: Registered fault name.
        **params: CLI option values (``bandwidth``, ``size``, ``loss``, ``rate``,
            ``corrupt``, ``skew``). Each builder uses only the keys it needs.

    Returns:
        A fault instance implementing the ``Fault`` protocol.
    """
    builder = _FAULT_BUILDERS.get(fault_name)
    if builder is None:
        return FAULTS[fault_name]
    return builder(**params)


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
    size: int = typer.Option(
        1024,
        "--size",
        "-s",
        help="Fill size in MiB (disk.fill only). Max 1048576 MiB (1 TiB).",
        min=1,
        max=1_048_576,
    ),
    loss: int = typer.Option(
        10,
        "--loss",
        "-l",
        help="Packet loss percentage (net.packet-loss only).",
        min=1,
        max=100,
    ),
    rate: int = typer.Option(
        1000,
        "--rate",
        help="Bandwidth cap in kbps (net.bandwidth only).",
        min=1,
    ),
    corrupt: int = typer.Option(
        1,
        "--corrupt",
        help="Packet corruption percentage (net.corrupt only).",
        min=1,
        max=100,
    ),
    skew: int = typer.Option(
        3600,
        "--skew",
        help="Clock skew in seconds (neg=backward). Non-zero; ±31536000s max.",
        min=-31_536_000,
        max=31_536_000,
    ),
    config_path: Path | None = typer.Option(
        None,
        "--config",
        help="Path to config.toml (default: $XDG_CONFIG_HOME/kvmchaos/config.toml).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Bypass allowlist and rate-limit checks. Use with care.",
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
        size: Fill size in MiB, used only by disk.fill.
        loss: Packet loss percentage, used only by net.packet-loss.
        rate: Bandwidth cap in kbps, used only by net.bandwidth.
        corrupt: Packet corruption percentage, used only by net.corrupt.
        skew: Clock offset in seconds, used only by clock.skew.
        config_path: Optional override for the config file location.
        force: If True, bypass allowlist and rate-limit checks.
    """
    configure_logging()

    if fault_name not in FAULTS:
        typer.echo(
            f"Unknown fault: {fault_name!r}. Known faults: {', '.join(sorted(FAULTS))}",
            err=True,
        )
        raise typer.Exit(code=2)
    if fault_name == "clock.skew" and skew == 0:
        typer.echo("--skew 0 is a no-op; provide a non-zero offset.", err=True)
        raise typer.Exit(code=2)
    fault_params: dict[str, object] = {
        "bandwidth": bandwidth,
        "size": size,
        "loss": loss,
        "rate": rate,
        "corrupt": corrupt,
        "skew": skew,
    }
    fault = _build_fault(fault_name, **fault_params)  # type: ignore[arg-type]

    if not force:
        try:
            cfg = load_config(config_path)
        except FileNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        if not cfg.allowlist.is_allowed(vm):
            typer.echo(
                f"VM {vm!r} is not in the allowlist. Add it to the config file or pass --force.",
                err=True,
            )
            raise typer.Exit(code=2)
        if cfg.rate_limit.is_configured():
            records = load_records(default_runs_dir())
            violation = rate_limit_violation(
                cfg.rate_limit, records, is_destructive=fault.destructive
            )
            if violation is not None:
                typer.echo(f"{violation}. Wait and retry, or pass --force.", err=True)
                raise typer.Exit(code=2)

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
            fault.inject,
            domain,
            action="inject",
            fault_name=fault_name,
            vm=vm,
            dry_run=dry_run,
            inject_params=fault_params,
            duration_s=duration,
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

        def _sigterm_handler(signum: int, frame: object) -> None:
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, _sigterm_handler)

        interrupted = False
        try:
            if dry_run:
                typer.echo(f"[dry-run] would: hold {fault_name} on {vm} for {duration}s")
            elif duration > 0:
                typer.echo(f"Holding '{fault_name}' on '{vm}' for {duration}s …")
                time.sleep(duration)
        except KeyboardInterrupt:
            interrupted = True
            typer.echo("\nInterrupted — reverting …", err=True)
        finally:
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
            fault_name,
            vm,
            resolved_uri,
            dry_run,
            started_at,
            ended_at,
            steps,
            interrupted=interrupted,
        )
        if interrupted:
            raise typer.Exit(code=1)


@app.command("run")
def run_cmd(
    ctx: typer.Context,
    experiment_path: Path = typer.Argument(
        ..., metavar="EXPERIMENT", help="Path to a TOML experiment file."
    ),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Validate and print plan without touching libvirt."
    ),
    config_path: Path | None = typer.Option(
        None,
        "--config",
        help="Path to config.toml (default: $XDG_CONFIG_HOME/kvmchaos/config.toml).",
    ),
    force: bool = typer.Option(False, "--force", help="Bypass allowlist and rate-limit checks."),
) -> None:
    """Run a TOML experiment: a sequence of ``inject`` steps.

    Each step runs its full inject → verify → hold → revert cycle before
    the next step begins. A step failure stops the experiment unless the
    step sets ``continue_on_failure = true``.

    See ``docs/examples/experiment.toml`` for schema and
    ``docs/recipes/`` for worked examples.

    Args:
        ctx: Typer context; carries the ``--connect`` URI.
        experiment_path: Path to a TOML experiment file.
        assume_yes: If True, skip the per-experiment confirmation prompt.
        dry_run: If True, validate everything but make no libvirt calls.
        config_path: Optional override for the config file location.
        force: If True, bypass allowlist and rate-limit checks.
    """
    configure_logging()

    try:
        experiment = load_experiment(experiment_path)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"experiment error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    for i, step in enumerate(experiment.steps, start=1):
        if step.fault not in FAULTS:
            typer.echo(
                f"experiment error: step {i} unknown fault {step.fault!r}. "
                f"Known: {', '.join(sorted(FAULTS))}",
                err=True,
            )
            raise typer.Exit(code=2)

    raw_uri = ctx.obj.get(_CTX_KEY) if ctx.obj else None
    resolved_uri = resolve_uri(raw_uri)

    typer.echo(f"Experiment: {experiment.name}")
    if experiment.description:
        typer.echo(f"  {experiment.description}")
    typer.echo(f"  {len(experiment.steps)} step(s), uri: {resolved_uri}")
    for i, step in enumerate(experiment.steps, start=1):
        marker = " [continue_on_failure]" if step.continue_on_failure else ""
        typer.echo(f"  {i:>2}. {step.fault} on {step.vm} (duration={step.duration}s){marker}")

    if not dry_run and not confirm("Run this experiment?", assume_yes=assume_yes):
        typer.echo("Aborted.")
        raise typer.Exit(code=1)

    exp_t0 = time.monotonic()
    exp_status = "ok"
    _obs_emit(
        obs_events.EXPERIMENT_START,
        recipe_path=str(experiment_path),
        step_count=len(experiment.steps),
    )

    failed_steps = 0
    try:
        for i, step in enumerate(experiment.steps, start=1):
            typer.echo(f"\n--- step {i}/{len(experiment.steps)}: {step.fault} on {step.vm} ---")
            try:
                _run_experiment_step(
                    step,
                    resolved_uri=resolved_uri,
                    dry_run=dry_run,
                    config_path=config_path,
                    force=force,
                )
            except typer.Exit as exc:
                failed_steps += 1
                code = exc.exit_code if isinstance(exc.exit_code, int) else 1
                if step.continue_on_failure:
                    typer.echo(
                        f"step {i} failed (exit {code}); continuing (continue_on_failure=true).",
                        err=True,
                    )
                    continue
                typer.echo(f"step {i} failed (exit {code}); stopping experiment.", err=True)
                raise typer.Exit(code=1) from exc
    except Exception:
        exp_status = "error"
        raise
    finally:
        _obs_emit(
            obs_events.EXPERIMENT_END,
            recipe_path=str(experiment_path),
            status=exp_status,
            elapsed_s=round(time.monotonic() - exp_t0, 3),
        )

    if failed_steps:
        typer.echo(f"\nExperiment finished with {failed_steps} failure(s).", err=True)
        raise typer.Exit(code=1)
    typer.echo("\nExperiment complete.")


def _run_experiment_step(
    step: Step,
    *,
    resolved_uri: str,
    dry_run: bool,
    config_path: Path | None,
    force: bool,
) -> None:
    """Execute a single experiment step.

    Duplicates the core inject orchestration from ``inject_cmd`` (URI
    check, safety, connect, inject/verify/hold/revert, record writing).
    Extraction into a single helper is future work; the duplication is
    contained and mechanically obvious.

    Args:
        step: Experiment step to execute.
        resolved_uri: Already-resolved libvirt URI.
        dry_run: If True, print plan only.
        config_path: Optional config file override.
        force: If True, bypass safety checks.

    Raises:
        typer.Exit: On any failure (propagated for experiment-level handling).
    """
    if step.fault == "clock.skew" and step.skew == 0:
        typer.echo("--skew 0 is a no-op; provide a non-zero offset.", err=True)
        raise typer.Exit(code=2)

    fault = _build_fault(
        step.fault,
        bandwidth=step.bandwidth,
        size=step.size,
        loss=step.loss,
        rate=step.rate,
        corrupt=step.corrupt,
        skew=step.skew,
    )

    if not force:
        try:
            cfg = load_config(config_path)
        except FileNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        if not cfg.allowlist.is_allowed(step.vm):
            typer.echo(
                f"VM {step.vm!r} is not in the allowlist. "
                "Add it to the config file or pass --force.",
                err=True,
            )
            raise typer.Exit(code=2)
        if cfg.rate_limit.is_configured():
            records = load_records(default_runs_dir())
            violation = rate_limit_violation(
                cfg.rate_limit, records, is_destructive=fault.destructive
            )
            if violation is not None:
                typer.echo(f"{violation}. Wait and retry, or pass --force.", err=True)
                raise typer.Exit(code=2)

    if fault.local_only and _is_remote(resolved_uri):
        typer.echo(
            f"{step.fault} requires local execution — run kvmchaos directly on the KVM host.",
            err=True,
        )
        raise typer.Exit(code=2)

    with connect(resolved_uri) as conn:
        try:
            domain = conn.lookupByName(step.vm)
        except libvirt.libvirtError as exc:
            typer.echo(f"VM '{step.vm}' not found: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        started_at = datetime.now(UTC)
        steps_records: list[dict[str, object]] = []

        inject_step = _run_step(
            fault.inject,
            domain,
            action="inject",
            fault_name=step.fault,
            vm=step.vm,
            dry_run=dry_run,
        )
        steps_records.append(inject_step)
        if inject_step["result"] == "fail":
            ended_at = datetime.now(UTC)
            _write_and_print_record(
                step.fault, step.vm, resolved_uri, dry_run, started_at, ended_at, steps_records
            )
            raise typer.Exit(code=1)

        verify_step = _run_step(
            fault.verify,
            domain,
            action="verify",
            fault_name=step.fault,
            vm=step.vm,
            dry_run=dry_run,
        )
        steps_records.append(verify_step)
        if verify_step["result"] == "fail":
            revert_step = _run_step(
                fault.revert,
                domain,
                action="revert",
                fault_name=step.fault,
                vm=step.vm,
                dry_run=dry_run,
            )
            steps_records.append(revert_step)
            ended_at = datetime.now(UTC)
            _write_and_print_record(
                step.fault, step.vm, resolved_uri, dry_run, started_at, ended_at, steps_records
            )
            raise typer.Exit(code=1)

        if dry_run:
            typer.echo(f"[dry-run] would: hold {step.fault} on {step.vm} for {step.duration}s")
        else:
            typer.echo(f"Holding '{step.fault}' on '{step.vm}' for {step.duration}s …")
            try:
                time.sleep(step.duration)
            except KeyboardInterrupt:
                typer.echo("Hold interrupted; reverting.", err=True)

        revert_step = _run_step(
            fault.revert,
            domain,
            action="revert",
            fault_name=step.fault,
            vm=step.vm,
            dry_run=dry_run,
        )
        steps_records.append(revert_step)
        ended_at = datetime.now(UTC)
        _write_and_print_record(
            step.fault, step.vm, resolved_uri, dry_run, started_at, ended_at, steps_records
        )
        if revert_step["result"] == "fail":
            raise typer.Exit(code=1)


def _run_step(
    func: Callable[[libvirt.virDomain], None],
    domain: libvirt.virDomain,
    *,
    action: str,
    fault_name: str,
    vm: str,
    dry_run: bool = False,
    inject_params: dict[str, object] | None = None,
    duration_s: int | None = None,
) -> dict[str, object]:
    """Execute one fault step (inject, verify, or revert) and log the outcome.

    Args:
        func: Callable to invoke — one of ``fault.inject``, ``.verify``, ``.revert``.
        domain: Live libvirt domain handle.
        action: Event label (``'inject'``, ``'verify'``, or ``'revert'``).
        fault_name: Fault registry key, included in the log event.
        vm: VM name, included in the log event.
        dry_run: If True, print a plan line and return without calling func or logging.
        inject_params: Fault-specific parameters (inject action only), included in the
            ``inject.start`` event payload.
        duration_s: Seconds the fault will be held (inject action only), included in
            the ``inject.start`` event payload.

    Returns:
        Dict with ``action``, ``result`` (``'ok'``, ``'fail'``, or ``'skipped'``),
        ``duration_ms``, and optional ``error``.
    """
    if dry_run:
        typer.echo(f"[dry-run] would: {action} {fault_name} on {vm}")
        return {"action": action, "result": "skipped", "duration_ms": 0}

    start_event_map = {
        "inject": obs_events.INJECT_START,
        "revert": None,
        "verify": None,
    }
    success_event_map = {
        "inject": obs_events.INJECT_SUCCESS,
        "revert": obs_events.REVERT_SUCCESS,
        "verify": None,
    }
    error_event_map = {
        "inject": obs_events.INJECT_ERROR,
        "revert": obs_events.REVERT_ERROR,
        "verify": None,
    }

    start_event = start_event_map.get(action)
    if start_event is not None:
        extra: dict[str, object] = {"fault": fault_name, "vm": vm}
        if inject_params is not None:
            extra["params"] = inject_params
        if duration_s is not None:
            extra["duration_s"] = duration_s
        _obs_emit(start_event, **extra)

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
        err_event = error_event_map.get(action)
        if err_event is not None:
            _obs_emit(
                err_event,
                fault=fault_name,
                vm=vm,
                error=str(exc),
                error_type=type(exc).__name__,
                elapsed_s=round(duration_ms / 1000, 3),
            )
        typer.echo(f"{action} error: {exc}", err=True)
        return {"action": action, "result": "fail", "duration_ms": duration_ms, "error": str(exc)}
    duration_ms = int((time.monotonic() - t0) * 1000)
    log_event(action=action, fault=fault_name, vm=vm, result="ok", duration_ms=duration_ms)
    ok_event = success_event_map.get(action)
    if ok_event is not None:
        _obs_emit(
            ok_event,
            fault=fault_name,
            vm=vm,
            elapsed_s=round(duration_ms / 1000, 3),
        )
    return {"action": action, "result": "ok", "duration_ms": duration_ms}


def _write_and_print_record(
    fault_name: str,
    vm: str,
    uri: str,
    dry_run: bool,
    started_at: datetime,
    ended_at: datetime,
    steps: list[dict[str, object]],
    *,
    interrupted: bool = False,
) -> None:
    """Build the run record dict, write it to disk, and print its path.

    The ``outcome`` field is ``"fail"`` if any step failed, ``"dry_run"`` if
    the run was a dry-run with no failures, ``"interrupted"`` if the hold was
    cancelled by the user, and ``"success"`` otherwise.

    Args:
        fault_name: Name of the fault that was injected.
        vm: Target VM name.
        uri: Resolved libvirt URI used for the run.
        dry_run: True if the run was a dry-run.
        started_at: UTC datetime when inject_cmd began executing steps.
        ended_at: UTC datetime when the final step completed.
        steps: List of step result dicts from ``_run_step``.
        interrupted: True if a KeyboardInterrupt cut the hold short.
    """
    if any(s["result"] == "fail" for s in steps):
        outcome = "fail"
    elif interrupted:
        outcome = "interrupted"
    elif dry_run:
        outcome = "dry_run"
    else:
        outcome = "success"
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
