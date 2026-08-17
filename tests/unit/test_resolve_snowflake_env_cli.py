"""Tests for `edgar-warehouse resolve-snowflake-env`.

This command exists so infra scripts stop reimplementing Snowflake
credential resolution -- it's a thin CLI wrapper around
SnowflakeConnectionSettings.from_env(), the same resolution chain already
trusted by `mdm export`/`mdm sync-graph`. See
tests/mdm/test_export.py for the underlying chain's own env-var/JSON-secret
coverage; these tests cover what's new here: the SnowCLI connections.toml
file-parsing path (previously untested anywhere), the --connection flag,
and the "never leak a bare password" output contract.
"""
from __future__ import annotations

import os
import sys

import pytest

from edgar_warehouse.cli import main


def _clear_snowflake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("SNOWFLAKE_CONNECTION", raising=False)


def _write_connections_toml(home, connections: dict[str, dict[str, str]]) -> None:
    snowflake_dir = home / ".snowflake"
    snowflake_dir.mkdir(parents=True, exist_ok=True)
    body_parts = []
    for name, fields in connections.items():
        lines = [f"[{name}]"]
        lines.extend(f'{key} = "{value}"' for key, value in fields.items())
        body_parts.append("\n".join(lines))
    (snowflake_dir / "connections.toml").write_text("\n\n".join(body_parts) + "\n")


def _write_config_toml(home, default_connection_name: str) -> None:
    snowflake_dir = home / ".snowflake"
    snowflake_dir.mkdir(parents=True, exist_ok=True)
    (snowflake_dir / "config.toml").write_text(
        f'default_connection_name = "{default_connection_name}"\n'
    )


def test_resolves_from_connections_toml_via_explicit_connection_flag(monkeypatch, tmp_path, capsys):
    _clear_snowflake_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_connections_toml(
        tmp_path,
        {
            "testconn": {
                "account": "acct-1",
                "user": "user-1",
                "password": "s3cr3t",
                "database": "EDGARTOOLS_PROD",
                "warehouse": "LOAD_WH",
                "role": "EDGARTOOLS_PROD_LOADER",
            }
        },
    )

    exit_code = main(["resolve-snowflake-env", "--connection", "testconn"])

    assert exit_code == 0
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert lines == [
        "export DBT_SNOWFLAKE_ACCOUNT=acct-1",
        "export DBT_SNOWFLAKE_USER=user-1",
        "export DBT_SNOWFLAKE_PASSWORD=s3cr3t",
        "export DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_PROD",
        "export DBT_SNOWFLAKE_WAREHOUSE=LOAD_WH",
        "export TF_VAR_snowflake_password=s3cr3t",
        "export DBT_SNOWFLAKE_ROLE=EDGARTOOLS_PROD_LOADER",
    ]
    # Every line is `export KEY=VALUE` shell code, never a bare human-readable
    # "password: ..." print -- output is meant only for eval "$(...)".
    assert all(line.startswith("export ") for line in lines)


def test_resolves_from_connections_toml_via_config_toml_default(monkeypatch, tmp_path, capsys):
    """The modern split-file SnowCLI layout: connections.toml holds the
    password, config.toml holds only default_connection_name. This is the
    exact layout deploy-snowflake-stack.sh's own resolver silently fails on
    today (see the architecture review) -- proving this path works is the
    point of this ticket.
    """
    _clear_snowflake_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_connections_toml(
        tmp_path,
        {"myconn": {"account": "acct-2", "user": "user-2", "password": "hunter2", "database": "EDGARTOOLS_PROD", "warehouse": "LOAD_WH"}},
    )
    _write_config_toml(tmp_path, default_connection_name="myconn")

    exit_code = main(["resolve-snowflake-env"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "export DBT_SNOWFLAKE_PASSWORD=hunter2" in out
    assert "export TF_VAR_snowflake_password=hunter2" in out


def test_env_var_override_takes_precedence_over_connections_toml(monkeypatch, tmp_path, capsys):
    _clear_snowflake_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_connections_toml(
        tmp_path,
        {
            "testconn": {
                "account": "toml-acct",
                "user": "toml-user",
                "password": "toml-password",
                "database": "EDGARTOOLS_PROD",
                "warehouse": "LOAD_WH",
            }
        },
    )
    monkeypatch.setenv("DBT_SNOWFLAKE_PASSWORD", "env-password")

    exit_code = main(["resolve-snowflake-env", "--connection", "testconn"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "export DBT_SNOWFLAKE_PASSWORD=env-password" in out
    assert "export TF_VAR_snowflake_password=env-password" in out
    assert "toml-password" not in out


def test_unknown_connection_fails_loudly_with_no_partial_output(monkeypatch, tmp_path, capsys):
    _clear_snowflake_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_connections_toml(
        tmp_path,
        {"otherconn": {"account": "a", "user": "u", "password": "p", "database": "D", "warehouse": "W"}},
    )

    exit_code = main(["resolve-snowflake-env", "--connection", "does-not-exist"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err
    assert "MDM_SNOWFLAKE_PASSWORD or DBT_SNOWFLAKE_PASSWORD" in captured.err


def test_connection_flag_does_not_leak_into_process_environment_after_the_call(monkeypatch, tmp_path):
    _clear_snowflake_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_connections_toml(
        tmp_path,
        {"testconn": {"account": "a", "user": "u", "password": "p", "database": "D", "warehouse": "W"}},
    )

    main(["resolve-snowflake-env", "--connection", "testconn"])

    assert "SNOWFLAKE_CONNECTION" not in os.environ


def test_refuses_to_print_credentials_to_an_interactive_terminal(monkeypatch, tmp_path, capsys):
    """The real safety property: even a correctly-configured connection must not
    reach a human's screen if invoked bare (no eval "$(...)"/source <(...) wrapper).
    Checked before any resolution happens, so no fixture toml is needed here.
    """
    _clear_snowflake_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    exit_code = main(["resolve-snowflake-env", "--connection", "testconn"])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "refusing to print" in captured.err
    assert 'eval "$(edgar-warehouse resolve-snowflake-env' in captured.err


def test_connection_flag_restores_a_previously_set_snowflake_connection_after_the_call(monkeypatch, tmp_path):
    _clear_snowflake_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SNOWFLAKE_CONNECTION", "outer-connection")
    _write_connections_toml(
        tmp_path,
        {"testconn": {"account": "a", "user": "u", "password": "p", "database": "D", "warehouse": "W"}},
    )

    main(["resolve-snowflake-env", "--connection", "testconn"])

    assert os.environ["SNOWFLAKE_CONNECTION"] == "outer-connection"
