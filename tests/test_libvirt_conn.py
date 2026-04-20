"""Tests for libvirt URI resolution and connection management."""

from unittest.mock import patch

import libvirt
import pytest

from kvmchaos.libvirt_conn import connect, resolve_uri


class TestResolveUri:
    def test_cli_flag_wins(self):
        with patch.dict("os.environ", {"LIBVIRT_DEFAULT_URI": "qemu:///session"}):
            assert resolve_uri("test:///default") == "test:///default"

    def test_env_var_used_when_no_flag(self):
        with patch.dict("os.environ", {"LIBVIRT_DEFAULT_URI": "qemu:///session"}):
            assert resolve_uri(None) == "qemu:///session"

    def test_default_when_nothing_set(self):
        with patch.dict("os.environ", {}, clear=True):
            assert resolve_uri(None) == "qemu:///system"


class TestConnect:
    def test_connects_to_test_driver(self):
        with connect("test:///default") as conn:
            assert isinstance(conn, libvirt.virConnect)
            assert conn.listAllDomains() != []

    def test_closes_on_exit(self):
        with connect("test:///default") as conn:
            pass
        with pytest.raises(libvirt.libvirtError):
            conn.listAllDomains()

    def test_closes_on_exception(self):
        with pytest.raises(RuntimeError):  # noqa: SIM117
            with connect("test:///default") as conn:
                raise RuntimeError("boom")
        with pytest.raises(libvirt.libvirtError):
            conn.listAllDomains()

    def test_connect_raises_on_none_connection(self):
        from unittest.mock import patch

        exc = pytest.raises(libvirt.libvirtError, match="returned None")
        with patch("libvirt.open", return_value=None), exc, connect("test:///default"):
            pass
