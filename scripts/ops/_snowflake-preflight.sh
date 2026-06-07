#!/usr/bin/env bash
# _snowflake-preflight.sh — sourced by sync scripts; not run directly.
#
# Validates Snowflake credentials before attempting sync-graph.
# Supports two credential sources (checked in order):
#
#   1. Env vars:  MDM_SNOWFLAKE_ACCOUNT / DBT_SNOWFLAKE_ACCOUNT (+ USER, PASSWORD, DATABASE, WAREHOUSE)
#   2. ~/.snowflake/connections.toml — SNOWFLAKE_CONNECTION (default: snowconn)
#
# When using connections.toml, MDM_SNOWFLAKE_DATABASE must still be set
# explicitly because the connection entry typically omits it.
# Set it to your Snowflake database, e.g.:
#   export MDM_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV
#
# Call once after arg-parsing, only when SKIP_GRAPH_SYNC=false.

_check_snowflake_preflight() {
    local skip="${1:-false}"
    [[ "$skip" == "true" ]] && return 0

    local has_env_creds=false
    local has_cli_config=false
    local conn_name="${SNOWFLAKE_CONNECTION:-}"

    # Detect env-var credentials
    if [[ -n "${MDM_SNOWFLAKE_ACCOUNT:-}${DBT_SNOWFLAKE_ACCOUNT:-}" ]]; then
        has_env_creds=true
    fi

    # Detect ~/.snowflake/connections.toml
    local connections_toml="$HOME/.snowflake/connections.toml"
    if [[ -f "$connections_toml" ]]; then
        # Resolve connection name: SNOWFLAKE_CONNECTION → config.toml default → "snowconn"
        if [[ -z "$conn_name" ]]; then
            local config_toml="$HOME/.snowflake/config.toml"
            if [[ -f "$config_toml" ]]; then
                conn_name=$(grep -E '^default_connection_name' "$config_toml" \
                    | sed 's/.*= *"\?\([^"]*\)"\?.*/\1/' | tr -d '[:space:]')
            fi
            conn_name="${conn_name:-snowconn}"
        fi
        # Check the connection section exists
        if grep -q "^\[${conn_name}\]" "$connections_toml" 2>/dev/null; then
            has_cli_config=true
            export SNOWFLAKE_CONNECTION="$conn_name"
        fi
    fi

    if [[ "$has_env_creds" == "false" && "$has_cli_config" == "false" ]]; then
        printf '\n\e[31m✗  Snowflake credentials not found.\e[0m\n' >&2
        printf '   Option A — env vars:\n' >&2
        printf '     export MDM_SNOWFLAKE_ACCOUNT=<account>\n' >&2
        printf '     export MDM_SNOWFLAKE_USER=<user>\n' >&2
        printf '     export MDM_SNOWFLAKE_PASSWORD=<password>\n' >&2
        printf '     export MDM_SNOWFLAKE_DATABASE=<database>\n' >&2
        printf '     export MDM_SNOWFLAKE_WAREHOUSE=<warehouse>\n' >&2
        printf '   Option B — Snowflake CLI config (connections.toml already present):\n' >&2
        printf '     export MDM_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV   # still required\n' >&2
        printf '     (account/user/password/warehouse come from [snowconn])\n' >&2
        printf '   Or re-run with --skip-graph-sync to skip Snowflake steps.\n\n' >&2
        return 1
    fi

    if [[ "$has_cli_config" == "true" && -z "${MDM_SNOWFLAKE_DATABASE:-}${DBT_SNOWFLAKE_DATABASE:-}" ]]; then
        printf '\n\e[31m✗  MDM_SNOWFLAKE_DATABASE is not set.\e[0m\n' >&2
        printf '   Credentials will come from ~/.snowflake/connections.toml [%s]\n' "$conn_name" >&2
        printf '   but the database name is not in the connection entry.\n' >&2
        printf '   Fix:\n' >&2
        printf '     export MDM_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV\n' >&2
        printf '   Or re-run with --skip-graph-sync to skip Snowflake steps.\n\n' >&2
        return 1
    fi

    # Report what we found
    if [[ "$has_env_creds" == "true" ]]; then
        info "Snowflake creds   = env vars (MDM_SNOWFLAKE_ACCOUNT / DBT_SNOWFLAKE_ACCOUNT)"
    else
        info "Snowflake creds   = ~/.snowflake/connections.toml [$conn_name]"
        info "Snowflake DB      = ${MDM_SNOWFLAKE_DATABASE:-${DBT_SNOWFLAKE_DATABASE}}"
    fi
    return 0
}
