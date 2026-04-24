"""Shared pytest fixtures using libvirt's in-process test driver."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import libvirt
import pytest

from kvmchaos.observability import logging as obs_logging


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


@pytest.fixture(autouse=True)
def _reset_observability_logging() -> Iterator[None]:
    """Reset observability logger state before each test."""
    from kvmchaos.observability import set_notifier

    obs_logging._reset_for_tests()
    set_notifier(None)
    yield
    obs_logging._reset_for_tests()
    set_notifier(None)


@pytest.fixture(autouse=True)
def _reset_libvirt_registration() -> Iterator[None]:
    """Reset the libvirt error handler registration flag between tests.

    Prevents cross-test pollution of the module-level ``_HANDLER_REGISTERED``
    flag that ``_register_once`` sets.
    """
    from kvmchaos import libvirt_conn

    libvirt_conn._reset_registration_for_tests()
    yield
    libvirt_conn._reset_registration_for_tests()
