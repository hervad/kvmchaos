"""Libvirt URI resolution and connection management.

The URI is resolved at call time with the precedence documented by `virsh`:
explicit argument → `LIBVIRT_DEFAULT_URI` env var → hardcoded default.
Keeping this in one place means the CLI, tests, and library callers all
agree on which hypervisor they are talking to.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import libvirt

DEFAULT_URI = "qemu:///system"


def resolve_uri(cli_flag: str | None) -> str:
    """Resolve the libvirt URI using CLI > env > default precedence.

    Args:
        cli_flag: Value of `--connect` if passed, else None.

    Returns:
        The URI string to pass to `libvirt.open`.
    """
    if cli_flag:
        return cli_flag
    env = os.environ.get("LIBVIRT_DEFAULT_URI")
    if env:
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
    try:
        yield conn
    finally:
        # libvirt raises if close() is called twice; we trust the caller
        # not to close it inside the block.
        conn.close()
