#!/usr/bin/env bash
# Shared helpers sourced by every PR-1 verification script.
# Strict mode and pretty logging — match the existing infra/scripts/ convention.

set -euo pipefail
IFS=$'\n\t'

# Colors only if stderr is a TTY (logs go to stderr, so check fd 2)
if [[ -t 2 ]]; then
    C_GREEN=$'\e[32m'
    C_RED=$'\e[31m'
    C_YELLOW=$'\e[33m'
    C_BLUE=$'\e[36m'
    C_BOLD=$'\e[1m'
    C_RESET=$'\e[0m'
else
    C_GREEN=""
    C_RED=""
    C_YELLOW=""
    C_BLUE=""
    C_BOLD=""
    C_RESET=""
fi

# Pass/fail counters — each script tracks its own.
PASS_COUNT=0
FAIL_COUNT=0

# Repo root — assume scripts run from any cwd; resolve via this file's dir.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." &> /dev/null && pwd)"

# ────────────────────────────────────────────────────────────────────
# Output helpers
# ────────────────────────────────────────────────────────────────────

step() {
    printf '\n%s── %s ──%s\n' "${C_BOLD}" "$*" "${C_RESET}" >&2
}

log() {
    printf '%s[verify-pr1]%s %s\n' "${C_BLUE}" "${C_RESET}" "$*" >&2
}

ok() {
    printf '  %s✓%s %s\n' "${C_GREEN}" "${C_RESET}" "$*" >&2
    PASS_COUNT=$((PASS_COUNT + 1))
}

fail_check() {
    printf '  %s✗%s %s\n' "${C_RED}" "${C_RESET}" "$*" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

warn() {
    printf '  %s!%s %s\n' "${C_YELLOW}" "${C_RESET}" "$*" >&2
}

fatal() {
    printf '%s[verify-pr1 FATAL]%s %s\n' "${C_RED}" "${C_RESET}" "$*" >&2
    exit 2
}

# ────────────────────────────────────────────────────────────────────
# Summary printer — call at the end of each stage script
# ────────────────────────────────────────────────────────────────────

print_summary() {
    local stage_name="$1"
    local total=$((PASS_COUNT + FAIL_COUNT))
    printf '\n' >&2
    if [[ $FAIL_COUNT -eq 0 ]]; then
        printf '%s%s[STAGE %s OK]%s %d/%d checks passed\n' \
            "${C_BOLD}" "${C_GREEN}" "$stage_name" "${C_RESET}" "$PASS_COUNT" "$total" >&2
        return 0
    else
        printf '%s%s[STAGE %s FAILED]%s %d/%d checks passed, %d failures\n' \
            "${C_BOLD}" "${C_RED}" "$stage_name" "${C_RESET}" \
            "$PASS_COUNT" "$total" "$FAIL_COUNT" >&2
        return 1
    fi
}

# ────────────────────────────────────────────────────────────────────
# Common assertions
# ────────────────────────────────────────────────────────────────────

# require_command <cmd> — bail out if a required tool is missing.
require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        fatal "required command not found: $1"
    fi
}

# require_file <path> — bail out if a required file is missing.
require_file() {
    if [[ ! -f "$1" ]]; then
        fatal "required file not found: $1"
    fi
}

# require_env <var-name> — bail out if a required env var is not set or empty.
require_env() {
    local var_name="$1"
    if [[ -z "${!var_name:-}" ]]; then
        fatal "required env var not set: $var_name"
    fi
}

# ────────────────────────────────────────────────────────────────────
# Snowflake CLI helpers (modern `snow` CLI, not legacy `snowsql`)
#
# The repo uses Snowflake CLI v3+ (snowflake-cli-labs / `snow`) — the same
# CLI invoked by infra/scripts/deploy-snowflake-stack.sh and
# scripts/test/smoke-test-single-cik.sh.  `snowsql` is deprecated; do not
# add it as a requirement to any new script.
#
# See docs/snowflake-cli-migration.md for the full migration rationale and
# the SQL-tokenizer contract.
#
# Required env: SNOW_CONNECTION (e.g. "edgartools-dev").
# Install: pip install snowflake-cli-labs
# Configure: `snow connection add` (writes config.toml under
#            ~/Library/Application Support/snowflake/ on macOS, or
#            ~/.snowflake/ on Linux — search order in snow_sql_file).
# ────────────────────────────────────────────────────────────────────

# snow_sql_exec <query> — run a query for side effect (suppress stdout).
# Returns the snow CLI exit code so callers can branch on success/failure.
snow_sql_exec() {
    require_env SNOW_CONNECTION
    snow sql --connection "$SNOW_CONNECTION" --query "$1" >/dev/null 2>&1
}

# snow_sql_file <path> — apply a SQL file via the snowflake-connector-python
# library (NOT the `snow` CLI).
#
# Why not `snow sql --filename` or `--stdin`: the bootstrap SQL files use
# Snowflake Scripting blocks (`BEGIN ... EXECUTE IMMEDIATE '...'; END;`),
# and the snow CLI's statement parser splits on `;` — including the `;` inside
# the EXECUTE IMMEDIATE string — which breaks the BEGIN/END block.
#
# Why we do NOT wrap BEGIN..END in EXECUTE IMMEDIATE $$ ... $$:
#   The bootstrap files reference session variables ($storage_integration_name,
#   $storage_role_arn, etc.) set via SET var='...' lines that
#   build_sql_with_vars prepends.  Those vars resolve at the TOP LEVEL of the
#   script — they do NOT resolve inside an EXECUTE IMMEDIATE string literal
#   (Snowflake treats the string as opaque until evaluation, by which time the
#   parent's session bindings are gone).  Wrapping the block makes
#   `$storage_integration_name` resolve as literal characters, not the value.
#
# Correct approach: split the file with a tokenizer that respects single
# quotes, dollar quotes, comments, AND BEGIN..END nesting — treat each
# top-level BEGIN..END block as one atomic statement and submit it to
# cur.execute() unwrapped.  The Python connector accepts anonymous blocks
# as a single statement; the server-side parser handles them correctly and
# the parent session vars resolve as expected.
#
# Reuses snow CLI's config.toml so no separate auth setup is needed.
# Resolves connection params from snow CLI's TOML config.  Search order:
#   $SNOWFLAKE_HOME/connections.toml     ← snow CLI ≥ v3 default
#   $SNOWFLAKE_HOME/config.toml          ← older snow CLI
#   ~/.snowflake/connections.toml        ← snow CLI ≥ v3 default
#   ~/.snowflake/config.toml             ← older snow CLI
#   ~/Library/Application Support/snowflake/config.toml   (macOS, legacy)
#   ~/.config/snowflake/config.toml      (XDG fallback)
#
# Two formats are supported:
#   connections.toml: top-level [<name>] section per connection
#   config.toml:      nested [connections.<name>] section per connection
snow_sql_file() {
    local sql_path="$1"
    # Prefer the repo's .venv python (has snowflake-connector-python installed)
    # over the system python3, which typically does not.
    local py_bin="python3"
    if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
        py_bin="${REPO_ROOT}/.venv/bin/python"
    elif [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
        py_bin="${VIRTUAL_ENV}/bin/python"
    fi
    "$py_bin" - "$sql_path" "$SNOW_CONNECTION" <<'PY' >/dev/null 2>&1
import os
import sys
from pathlib import Path

sql_path = Path(sys.argv[1])
connection_name = sys.argv[2]

try:
    import tomllib
except ImportError:
    import tomli as tomllib

# Build search path list, in priority order.  Newer snow CLI uses
# connections.toml (top-level [name]); older versions use config.toml
# with nested [connections.name].  We try both at each location.
home = Path.home()
candidates = []
if os.environ.get("SNOWFLAKE_HOME"):
    sh = Path(os.environ["SNOWFLAKE_HOME"])
    candidates += [sh / "connections.toml", sh / "config.toml"]
candidates += [
    home / ".snowflake" / "connections.toml",
    home / ".snowflake" / "config.toml",
    home / "Library" / "Application Support" / "snowflake" / "connections.toml",
    home / "Library" / "Application Support" / "snowflake" / "config.toml",
    home / ".config" / "snowflake" / "connections.toml",
    home / ".config" / "snowflake" / "config.toml",
]

conn_params = None
chosen_path = None
for p in candidates:
    if not p.is_file():
        continue
    with open(p, "rb") as f:
        cfg = tomllib.load(f)
    # connections.toml: top-level [<name>] tables
    # config.toml:      nested [connections.<name>] tables
    if p.name == "connections.toml":
        candidate = cfg.get(connection_name)
    else:
        candidate = cfg.get("connections", {}).get(connection_name)
    if isinstance(candidate, dict):
        conn_params = candidate
        chosen_path = p
        break

if conn_params is None:
    print(f"snow connection '{connection_name}' not found in any of: "
          f"{[str(p) for p in candidates if p.is_file()]}", file=sys.stderr)
    sys.exit(2)

import snowflake.connector as sf

# Forward every TOML field as a kwarg to sf.connect() — Snowflake's connector
# accepts arbitrary auth-related params (authenticator, token, private_key_*,
# client_store_temporary_credential, etc.), so we shouldn't whitelist a
# fixed set.
connect_kwargs = dict(conn_params)

# Allow env-var override / fallback for password (legacy)
env_pw = os.environ.get("SNOWFLAKE_PASSWORD")
if env_pw and not connect_kwargs.get("password"):
    connect_kwargs["password"] = env_pw

# Auto-fallback: if the snow CLI is configured for an interactive OAuth/SSO
# flow (e.g. OAUTH_AUTHORIZATION_CODE, externalbrowser) AND a password is
# present in the same connection profile, prefer password auth here.  The
# Python connector cannot reuse the snow CLI's OAuth token cache, so without
# this fallback the connector would launch a fresh browser auth flow on
# every invocation — defeating the harness's non-interactive contract.
# Production / CI auth (service-account password, key-pair) is unaffected
# because those connections don't set an OAuth-style authenticator.
auth_method = (connect_kwargs.get("authenticator") or "").upper()
interactive_oauth = auth_method in {
    "OAUTH_AUTHORIZATION_CODE",
    "EXTERNALBROWSER",
}
if interactive_oauth and connect_kwargs.get("password"):
    # Force password auth: drop OAuth-specific fields.
    connect_kwargs.pop("authenticator", None)
    connect_kwargs.pop("client_store_temporary_credential", None)

# An empty-string password trips connector validation when an authenticator
# like OAUTH_AUTHORIZATION_CODE is configured.  Strip it.
if connect_kwargs.get("password") in (None, ""):
    connect_kwargs.pop("password", None)

conn = sf.connect(**connect_kwargs)
try:
    sql_text = sql_path.read_text()

    # Tokenize the file into atomic top-level statements.
    #
    # State machine respects:
    #   - single-quoted strings ('...' with '' as escaped quote)
    #   - dollar-quoted strings ($$...$$ and $tag$...$tag$)
    #   - SQL line comments (-- to end of line)
    #   - SQL block comments (/* ... */)
    #   - BEGIN..END nesting — keeps the whole Snowflake Scripting block
    #     as one atomic statement so internal `;` (e.g. inside
    #     EXECUTE IMMEDIATE 'CREATE ...';) do not prematurely split it.
    #
    # The Python connector's cur.execute() handles anonymous blocks
    # (BEGIN..END) as a single statement, and parent-session variables
    # (set via SET var='...') resolve correctly *only* when the block is
    # submitted unwrapped — wrapping in EXECUTE IMMEDIATE $$...$$ makes
    # the block contents opaque text and breaks session-variable
    # resolution.  See docs/snowflake-cli-migration.md for the full
    # rationale.

    def _is_word_boundary(text, idx):
        return idx < 0 or idx >= len(text) or not (text[idx].isalnum() or text[idx] == "_")

    def _starts_with_kw(text, i, kw):
        n = len(text)
        if i + len(kw) > n:
            return False
        if text[i:i + len(kw)].lower() != kw.lower():
            return False
        return _is_word_boundary(text, i - 1) and _is_word_boundary(text, i + len(kw))

    def split_statements(text):
        stmts = []
        buf = []
        i = 0
        n = len(text)
        in_squote = False
        dollar_tag = None
        line_comment = False
        block_comment = False
        begin_depth = 0
        while i < n:
            ch = text[i]
            # ── inside line comment ───────────────────────────────
            if line_comment:
                buf.append(ch)
                i += 1
                if ch == "\n":
                    line_comment = False
                continue
            # ── inside block comment ──────────────────────────────
            if block_comment:
                buf.append(ch)
                i += 1
                if ch == "*" and i < n and text[i] == "/":
                    buf.append(text[i])
                    i += 1
                    block_comment = False
                continue
            # ── inside dollar-quoted string ───────────────────────
            if dollar_tag is not None:
                if text[i:i + len(dollar_tag)] == dollar_tag:
                    buf.append(text[i:i + len(dollar_tag)])
                    i += len(dollar_tag)
                    dollar_tag = None
                    continue
                buf.append(ch)
                i += 1
                continue
            # ── inside single-quoted string ───────────────────────
            if in_squote:
                buf.append(ch)
                i += 1
                if ch == "'":
                    if i < n and text[i] == "'":
                        # Escaped quote ('')
                        buf.append(text[i])
                        i += 1
                        continue
                    in_squote = False
                continue
            # ── top-level: detect comment / string / quote openers ─
            if ch == "-" and i + 1 < n and text[i + 1] == "-":
                line_comment = True
                buf.append(text[i:i + 2])
                i += 2
                continue
            if ch == "/" and i + 1 < n and text[i + 1] == "*":
                block_comment = True
                buf.append(text[i:i + 2])
                i += 2
                continue
            if ch == "'":
                in_squote = True
                buf.append(ch)
                i += 1
                continue
            if ch == "$":
                # Look for $$ or $tag$ opener.
                j = i + 1
                while j < n and (text[j].isalnum() or text[j] == "_"):
                    j += 1
                if j < n and text[j] == "$":
                    tag = text[i:j + 1]
                    buf.append(tag)
                    i = j + 1
                    dollar_tag = tag
                    continue
            # ── top-level: track BEGIN..END nesting ────────────────
            if _starts_with_kw(text, i, "BEGIN"):
                begin_depth += 1
                buf.append(text[i:i + 5])
                i += 5
                continue
            if _starts_with_kw(text, i, "END") and begin_depth > 0:
                # Distinguish bare `END` (closes BEGIN) from `END IF`,
                # `END LOOP`, `END FOR`, `END CASE`, `END WHILE`,
                # `END REPEAT` (close non-BEGIN constructs nested inside
                # the block).  A bare `END` is immediately followed by
                # whitespace + `;` (or EOF).  Anything else with a
                # following identifier means we're closing a sub-construct,
                # not the BEGIN block — preserve depth in that case.
                j = i + 3
                while j < n and text[j] in " \t":
                    j += 1
                bare_end = j >= n or text[j] == ";"
                buf.append(text[i:i + 3])
                i += 3
                if not bare_end:
                    # `END <kw>` — just emit the literal `END` and keep
                    # the begin_depth unchanged.
                    continue
                begin_depth -= 1
                # If this END terminates the outermost block, consume
                # the `;` as part of the block and emit the statement.
                if begin_depth == 0 and j < n and text[j] == ";":
                    buf.append(text[i:j + 1])
                    i = j + 1
                    stmt = "".join(buf).strip()
                    if stmt:
                        stmts.append(stmt)
                    buf = []
                continue
            # ── top-level: `;` ends a statement only when not inside BEGIN ─
            if ch == ";" and begin_depth == 0:
                stmt = "".join(buf).strip()
                if stmt:
                    stmts.append(stmt)
                buf = []
                i += 1
                continue
            buf.append(ch)
            i += 1
        tail = "".join(buf).strip()
        if tail:
            stmts.append(tail)
        return stmts

    def is_comment_only(stmt):
        """Return True if stmt contains only SQL comments and whitespace."""
        import re
        cleaned = re.sub(r"--[^\n]*", "", stmt)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
        return not cleaned.strip()

    cur = conn.cursor()
    try:
        for stmt in split_statements(sql_text):
            if is_comment_only(stmt):
                continue
            cur.execute(stmt)
    finally:
        cur.close()
finally:
    conn.close()
PY
}

# snow_scalar <query> — return the first column of the first row.
#
# Robust against transient `snow sql` flakiness: occasionally the CLI mixes
# warning/banner text into stdout (OAuth token refresh, deprecation notices)
# which corrupts the JSON.  We:
#   - retry up to 3 times on JSON parse failure
#   - extract only the [ ... ] block from stdout before parsing
#   - swallow Python errors and emit an empty string so callers see a clean
#     "this query returned nothing" rather than a noisy traceback
#
# Matches the helper pattern in scripts/test/smoke-test-single-cik.sh.
snow_scalar() {
    require_env SNOW_CONNECTION
    local query="$1"
    local attempt
    local json_output
    local result
    local py_extract='import json, re, sys
raw = sys.stdin.read()
m = re.search(r"\[.*\]", raw, re.DOTALL)
if not m:
    sys.exit(0)
try:
    rows = json.loads(m.group(0))
except json.JSONDecodeError:
    sys.exit(0)
if rows:
    print(list(rows[0].values())[0])'
    for attempt in 1 2 3; do
        json_output=$(snow sql --connection "$SNOW_CONNECTION" --format json --query "$query" 2>/dev/null)
        result=$(printf '%s' "$json_output" | python3 -c "$py_extract" 2>/dev/null)
        if [[ -n "$result" ]]; then
            printf '%s' "$result"
            return 0
        fi
    done
    printf '%s' "$result"
}
