"""Replace a function in a test so that a changed real signature fails the test.

A bare `lambda *a: ...` accepts any call, so the test keeps passing after the real function
changes its parameters. `checked` wraps the replacement in an autospec of the real function:
a call that the real function would refuse raises `TypeError` before the replacement runs.
"""
from unittest.mock import create_autospec


def checked(monkeypatch, owner, name, replacement):
    """Patch `owner.name` with `replacement`, called only with arguments the real function accepts.

    Patching a name again (a fixture used twice in one test) checks against the real function,
    not against the earlier replacement."""
    current = getattr(owner, name)
    real = getattr(current, "checked_original", current)
    patched = create_autospec(real, side_effect=replacement)
    patched.checked_original = real
    monkeypatch.setattr(owner, name, patched)
