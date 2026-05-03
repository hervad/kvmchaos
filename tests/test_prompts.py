"""Tests for the confirmation prompt."""

import io

from kvmchaos.prompts import confirm


def test_assume_yes_skips_prompt(capsys):
    assert confirm("Proceed?", assume_yes=True) is True
    assert capsys.readouterr().out == ""


def test_empty_input_defaults_to_no(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    assert confirm("Proceed?", assume_yes=False) is False


def test_y_accepts(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))
    assert confirm("Proceed?", assume_yes=False) is True


def test_yes_accepts_case_insensitive(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("YES\n"))
    assert confirm("Proceed?", assume_yes=False) is True


def test_anything_else_rejects(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("maybe\n"))
    assert confirm("Proceed?", assume_yes=False) is False
