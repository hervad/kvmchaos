"""Smoke test: package imports and exposes a version."""

import re

import kvmchaos


def test_version_is_semver():
    assert re.match(r"^\d+\.\d+\.\d+", kvmchaos.__version__)
