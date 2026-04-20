"""Shared pytest fixtures using libvirt's in-process test driver."""

import contextlib
from collections.abc import Iterator

import libvirt
import pytest


@pytest.fixture
def test_conn() -> Iterator[libvirt.virConnect]:
    """Open a connection to libvirt's in-process test driver.

    The test driver (`test:///default`) ships a pre-defined running domain
    named 'test'. No root access or real QEMU required.
    """
    conn = libvirt.open("test:///default")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def running_domain(test_conn: libvirt.virConnect) -> Iterator[libvirt.virDomain]:
    """Return the built-in 'test' domain, guaranteed to be in running state.

    Resets the domain to running before each test and cleans up after,
    so tests don't leak state into one another.
    """
    domain = test_conn.lookupByName("test")
    _ensure_running(domain)
    yield domain
    with contextlib.suppress(libvirt.libvirtError):
        _ensure_running(domain)  # Best-effort cleanup; test driver state is process-local


def _ensure_running(domain: libvirt.virDomain) -> None:
    """Transition a domain to the running state from any recoverable state."""
    state, _ = domain.state()
    if state == libvirt.VIR_DOMAIN_PAUSED:
        domain.resume()
    elif state == libvirt.VIR_DOMAIN_SHUTOFF:
        domain.create()
