"""Smoke test for `python -m kvmchaos` entry point."""

from __future__ import annotations

import runpy

import pytest


def test_main_module_dispatches_to_app() -> None:
    """Running `python -m kvmchaos` with no args should invoke the Typer app.

    Typer prints help and exits 2 when given no arguments (``no_args_is_help=True``).
    ``runpy.run_module`` raises ``SystemExit`` because the CLI calls ``sys.exit``.
    """
    with pytest.raises(SystemExit):
        runpy.run_module("kvmchaos", run_name="__main__")
