from types import SimpleNamespace

from edgar_warehouse.application import load_observer as observer


def test_missing_credentials_fail_before_reading_bookkeeping(monkeypatch, capsys):
    monkeypatch.delenv("OPENMETADATA_URL", raising=False)
    monkeypatch.delenv("OPENMETADATA_TOKEN", raising=False)
    args = SimpleNamespace(page_size=10, interval=1, duration=0)
    assert observer._observe(args) == 2
    assert 'Set OPENMETADATA_URL' in capsys.readouterr().out


def test_invalid_bounds_fail_without_a_load_or_remote_call(capsys):
    args = SimpleNamespace(page_size=0, interval=1, duration=0)
    assert observer._observe(args) == 2
    assert 'Invalid observation bounds' in capsys.readouterr().out
