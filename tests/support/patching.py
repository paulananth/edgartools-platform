"""Replace a function in a test so that a changed real signature fails the test.

A bare `lambda *a: ...` accepts any call, so the test keeps passing after the real function
changes its parameters. `checked` wraps the replacement in an autospec of the real function:
a call that the real function would refuse raises `TypeError` before the replacement runs.
"""
from unittest.mock import create_autospec


def checked(monkeypatch, owner, name, replacement):
    """Patch `owner.name` with `replacement`, called only with arguments the real function accepts."""
    monkeypatch.setattr(owner, name, create_autospec(getattr(owner, name), side_effect=replacement))
