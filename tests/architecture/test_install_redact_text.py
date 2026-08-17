"""Tests for install.sh's redact_text() -- the sed pipeline that scrubs
secrets from every stage's output before it reaches the terminal or the
report file (install.sh:341-351, called at lines 605, 903, 1042).

Previously untested. Written while verifying (per credential-isolation
Ticket 2's acceptance criteria) that redact_text correctly handles the
output shape `edgar-warehouse resolve-snowflake-env` actually emits --
`export KEY=VALUE` shell lines, where VALUE is optionally single-quoted by
Python's shlex.quote() whenever it contains a space or other shell-special
character.

That check surfaced a real, previously-undetected bug: the PASSWORD/TOKEN/
SECRET/API_KEY regex's value group was `[^[:space:]]+` -- it stopped at the
first whitespace, so a quoted value containing a space (e.g.
`PASSWORD='p@ss w0rd!'`) was only partially redacted, leaking everything
after the first space (` w0rd!'`) into the terminal/report. Fixed by
redacting to end-of-line instead of stopping at whitespace -- the safer
failure mode for a function whose whole job is hiding secrets. This file
locks that fix in and covers the function's other redaction categories so
a future edit can't silently regress any of them.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "infra" / "scripts" / "install.sh"


@pytest.fixture(scope="module")
def redact_text_script(tmp_path_factory) -> Path:
    """Extract just the redact_text() function body -- install.sh has no
    source-guard and runs top-level logic unconditionally, so it can't be
    sourced directly.
    """
    content = INSTALL_SH.read_text()
    start = content.index("redact_text() {")
    end = content.index("\n}\n", start) + len("\n}\n")
    func = content[start:end]
    assert "sed -E" in func, "extraction landed on the wrong function -- install.sh must have changed shape"

    script_path = tmp_path_factory.mktemp("redact") / "redact_text_extracted.sh"
    script_path.write_text("#!/usr/bin/env bash\n" + func)
    script_path.chmod(0o755)
    return script_path


def _redact(script_path: Path, text: str) -> str:
    result = subprocess.run(
        ["bash", "-c", f'source "{script_path}"; redact_text'],
        input=text,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_redacts_a_simple_unquoted_password(redact_text_script):
    out = _redact(redact_text_script, "export DBT_SNOWFLAKE_PASSWORD=hunter2\n")
    assert out == "export DBT_SNOWFLAKE_PASSWORD=<redacted>\n"


def test_redacts_a_password_containing_a_space_completely(redact_text_script):
    """Regression test for the bug this ticket found: a shlex.quote()'d
    value with an internal space used to leak everything after the space.
    """
    out = _redact(redact_text_script, "export DBT_SNOWFLAKE_PASSWORD='p@ss w0rd!'\n")
    assert out == "export DBT_SNOWFLAKE_PASSWORD=<redacted>\n"
    assert "w0rd" not in out
    assert "p@ss" not in out


def test_redacts_tf_var_snowflake_password_shape(redact_text_script):
    out = _redact(redact_text_script, "export TF_VAR_snowflake_password='p@ss w0rd!'\n")
    assert out == "export TF_VAR_snowflake_password=<redacted>\n"


def test_redacts_colon_delimited_secret_and_token(redact_text_script):
    out = _redact(redact_text_script, "SECRET:my-secret-value\nTOKEN:abc-def-123\n")
    assert out == "SECRET:<redacted>\nTOKEN:<redacted>\n"


def test_redacts_a_quoted_colon_delimited_value_containing_spaces(redact_text_script):
    out = _redact(redact_text_script, "SECRET:'my secret value'\n")
    assert out == "SECRET:<redacted>\n"


def test_does_not_swallow_a_separately_redacted_value_later_on_the_same_line(redact_text_script):
    """Regression test for a second bug found while fixing the first: an
    earlier draft redacted PASSWORD=/TOKEN=/SECRET= to end-of-line, which
    over-matched an unquoted bare-token password (no closing delimiter to
    bound it) and swallowed unrelated, separately-redacted content later on
    the same line -- e.g. an already-redacted sha256 image digest.
    """
    out = _redact(
        redact_text_script,
        "external_id = abc123 postgresql://user:pass@example.snowflake.app:5432/mdm "
        "password=secret token=tok sha256:" + ("a" * 64) + "\n",
    )
    assert out == (
        "external_id = <redacted-external-id> <redacted-dsn> "
        "password=<redacted> token=<redacted> <redacted-image-digest>\n"
    )


def test_resolver_connection_confirmation_line_passes_through_unredacted(redact_text_script):
    """No PASSWORD=/TOKEN=/SECRET= substring, no other redacted category --
    this is edgar-warehouse resolve-snowflake-env's own stderr line, which
    never contains the secret itself, only the connection name.
    """
    out = _redact(redact_text_script, "resolved Snowflake credentials for connection 'prod-connection'\n")
    assert out == "resolved Snowflake credentials for connection 'prod-connection'\n"


def test_bare_word_password_with_no_delimiter_is_left_alone(redact_text_script):
    out = _redact(redact_text_script, "the password field was empty\n")
    assert out == "the password field was empty\n"


def test_redacts_postgres_dsn(redact_text_script):
    out = _redact(redact_text_script, "postgresql://user:pw@host:5432/db\n")
    assert out == "<redacted-dsn>\n"


def test_redacts_s3_url(redact_text_script):
    out = _redact(redact_text_script, "s3://bucket/key/path\n")
    assert out == "<redacted-s3-url>\n"


def test_redacts_aws_arn(redact_text_script):
    out = _redact(redact_text_script, "arn:aws:iam::123456789012:role/deployer\n")
    assert out == "<redacted-arn>\n"


def test_redacts_bare_12_digit_account_id(redact_text_script):
    out = _redact(redact_text_script, "account 123456789012 is active\n")
    assert out == "account <redacted-account-id> is active\n"


def test_redacts_json_password_field(redact_text_script):
    out = _redact(redact_text_script, '{"password": "hunter2", "user": "app"}\n')
    assert out == '{"password": "<redacted>", "user": "app"}\n'
