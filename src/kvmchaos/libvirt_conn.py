"""Libvirt URI resolution and connection management.

The URI is resolved at call time with the precedence documented by `virsh`:
explicit argument → `LIBVIRT_DEFAULT_URI` env var → hardcoded default.
Keeping this in one place means the CLI, tests, and library callers all
agree on which hypervisor they are talking to.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

import libvirt

_LIBVIRT_LOG = logging.getLogger("kvmchaos.observability.libvirt")


def _libvirt_error_handler(_ctx: object, err: tuple) -> None:
    """Forward libvirt C-library errors to the observability logger.

    libvirt calls this for every error normally written to stderr via
    its C-level logging. Routing the message to our ``kvmchaos.observability
    .libvirt`` child logger at DEBUG keeps the information available
    under ``--verbose`` while silencing it in the default INFO mode.

    Args:
        _ctx: Opaque context pointer — unused; required by libvirt's signature.
        err: Tuple as documented in libvirt's ``virErrorSetCallback``.
            The first four fields are ``(code, domain, message, level)``.
    """
    code, domain, message, level, *_ = err
    _LIBVIRT_LOG.debug(
        message,
        extra={
            "event": "libvirt.stderr",
            "code": code,
            "domain": domain,
            "libvirt_level": level,
        },
    )


DEFAULT_URI = "qemu:///system"


def resolve_uri(cli_flag: str | None) -> str:
    """Resolve the libvirt URI using CLI > env > default precedence.

    Args:
        cli_flag: Value of `--connect` if passed, else None.

    Returns:
        The URI string to pass to `libvirt.open`.
    """
    if cli_flag is not None:
        return cli_flag
    env = os.environ.get("LIBVIRT_DEFAULT_URI")
    if env:  # empty env var is treated as unset
        return env
    return DEFAULT_URI


@contextmanager
def connect(uri: str | None = None) -> Iterator[libvirt.virConnect]:
    """Open a libvirt connection and close it on exit.

    Args:
        uri: Optional explicit URI. If None, `resolve_uri` is consulted.

    Yields:
        A live `libvirt.virConnect`. Closed automatically when the `with`
        block exits, including on exception.

    Raises:
        libvirt.libvirtError: If the connection cannot be opened.
    """
    resolved = resolve_uri(uri)
    conn = libvirt.open(resolved)
    if conn is None:
        # Reset any stale libvirt error state so our message is preserved.
        libvirt.virResetLastError()
        raise libvirt.libvirtError(f"libvirt.open({resolved!r}) returned None")
    try:
        yield conn
    finally:
        # libvirt raises if close() is called twice; we trust the caller
        # not to close it inside the with block.
        conn.close()  # conn is guaranteed non-None here
