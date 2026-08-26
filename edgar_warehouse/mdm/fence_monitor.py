"""Ticket 44 (change-propagation map): detect privilege drift on the
acquisition-ledger/registry tables Ticket 30 fenced `application`/
`snowflake_write` away from.

Ticket 30's own live incident proved two distinct failure shapes worth
watching for, not just one:

1. **A leak** -- `application` or `snowflake_write` regains SELECT/INSERT/
   UPDATE/DELETE on a fenced table (the failure Ticket 30 itself found and
   fixed: Snowflake-hosted Postgres re-grants `snowflake_write`'s baseline
   access to these tables as a side effect of any `RESET ACCESS` call).
2. **An operational access gap** -- a table's own owning role loses its own
   SELECT access, e.g. via a future re-provisioning that strips grants as a
   side effect of an unrelated change (the exact shape of the
   manifest-pipeline-ownership incident documented in CLAUDE.md, applied to
   a different table set). A monitor that only checks the deny side and
   never the allow side would report "clean" over a broken pipeline. See
   `OperationalAccessGap`'s own docstring for why this checks the owner
   role specifically, not every individual operational sub-role.

The fenced-table set is discovered live from `pg_class`/`pg_roles`, not
hardcoded -- Ticket 30's own comment in `013_acquisition_ledger.sql` is
explicit that a future migration adding another acquisition-ledger table
needs the same fencing repeated for it. A hardcoded table list here would
have exactly the `ShardedSilverReader._TABLES` failure mode CLAUDE.md
already documents: a new table lands, nobody updates the monitor, and the
monitor silently reports clean forever.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

# The two ambient, platform-managed identities Ticket 30 found bypass every
# per-object REVOKE this migration family issues. `application` is the
# shared runtime DSN every warehouse/MDM command connects with; every
# genuine acquisition read/write goes through an explicit `SET ROLE` into
# one of the operational sub-roles instead (see the migration files' own
# comments) -- so `application` itself should never show direct access.
MONITORED_AMBIENT_ROLES: tuple[str, ...] = ("application", "snowflake_write")

_PRIVILEGES: tuple[str, ...] = ("SELECT", "INSERT", "UPDATE", "DELETE")

# Matches both edgartools_acquisition_owner (013) and
# edgartools_acquisition_registry_owner (014) without naming either
# directly, so a future migration's differently-named owner role is picked
# up automatically.
_OWNER_ROLE_LIKE_PATTERN = "edgartools\\_acquisition%owner"


@dataclass(frozen=True)
class FenceLeak:
    """`role` currently holds `privilege` on `table`, despite Ticket 30's
    fencing having revoked it -- the failure this ticket exists to catch."""

    role: str
    table: str
    privilege: str


@dataclass(frozen=True)
class OperationalAccessGap:
    """`table`'s own owning role (`role`) can no longer SELECT its own
    table -- the allow-side failure a deny-only monitor would miss (the
    manifest-pipeline-ownership incident's shape, applied to this table
    set: an ownership/grant operation silently stripped access instead of
    just changing who holds it).

    Scoped deliberately to the owner role, not every individual operational
    sub-role (`edgartools_acquisition_processor` etc. for 013's tables):
    unlike the fenced-table set, discovering "which sub-roles currently hold
    a grant" from the grant state itself is circular -- a check reading the
    very thing it's trying to verify can't tell "no sub-role was ever
    supposed to have one" (014's tables, by design -- its owner role *is*
    the operational identity, see the module docstring) from "a sub-role's
    grant just got wiped." The owner is a non-circular signal instead,
    empirically confirmed: Postgres does not silently exempt an owner from
    ACL checks (a `REVOKE` genuinely strips a role's own privileges even on
    a table it owns), so the owner losing SELECT on its own table is
    concrete evidence a grant-stripping operation ran against these
    objects -- the same failure shape a sub-role-specific gap would come
    from, just detected at the identity guaranteed to exist for every
    fenced table rather than one that may or may not, per table."""

    table: str
    role: str


@dataclass(frozen=True)
class FenceCheckResult:
    fenced_tables: tuple[str, ...]
    owner_roles: tuple[str, ...]
    leaks: tuple[FenceLeak, ...]
    access_gaps: tuple[OperationalAccessGap, ...]

    @property
    def is_clean(self) -> bool:
        return not self.leaks and not self.access_gaps


def _role_exists(conn, role: str) -> bool:
    return bool(
        conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar()
    )


def _discover_owner_roles(conn) -> list[str]:
    rows = conn.execute(
        text(
            "SELECT DISTINCT pg_get_userbyid(c.relowner) AS owner "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' "
            "AND pg_get_userbyid(c.relowner) LIKE :pattern"
        ),
        {"pattern": _OWNER_ROLE_LIKE_PATTERN},
    ).fetchall()
    return sorted({row[0] for row in rows if row[0]})


def _discover_fenced_tables(conn, owner_roles: list[str]) -> dict[str, str]:
    """Returns {table_name: owning_role}, not just a bare list -- the owner
    per table is what the access-gap check below needs, and re-deriving it
    with a second query per table would be wasteful."""
    if not owner_roles:
        return {}
    stmt = text(
        "SELECT c.relname, pg_get_userbyid(c.relowner) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' "
        "AND pg_get_userbyid(c.relowner) IN :owners"
    ).bindparams(bindparam("owners", expanding=True))
    rows = conn.execute(stmt, {"owners": owner_roles}).fetchall()
    return {row[0]: row[1] for row in rows}


def _has_privilege(conn, role: str, table: str, privilege: str) -> bool:
    return bool(
        conn.execute(
            text("SELECT has_table_privilege(:role, :table, :priv)"),
            {"role": role, "table": table, "priv": privilege},
        ).scalar()
    )


def _find_leaks(conn, table_owners: dict[str, str]) -> list[FenceLeak]:
    leaks: list[FenceLeak] = []
    for role in MONITORED_AMBIENT_ROLES:
        if not _role_exists(conn, role):
            # snowflake_write does not exist on a plain/local/test Postgres
            # instance -- a genuine no-op there, not a gap in coverage.
            continue
        for table in table_owners:
            for privilege in _PRIVILEGES:
                if _has_privilege(conn, role, table, privilege):
                    leaks.append(FenceLeak(role=role, table=table, privilege=privilege))
    return leaks


def _find_access_gaps(conn, table_owners: dict[str, str]) -> list[OperationalAccessGap]:
    gaps: list[OperationalAccessGap] = []
    for table, owner in table_owners.items():
        if not _has_privilege(conn, owner, table, "SELECT"):
            gaps.append(OperationalAccessGap(table=table, role=owner))
    return gaps


def check_ledger_fence(engine: Engine) -> FenceCheckResult:
    """Run the full drift check: discover the fenced tables live, then check
    both the deny side (Ticket 30's own leak) and the allow side (a future
    grant-stripping operation breaking the owner's own access).

    Requires no privilege beyond what the ordinary `application` runtime
    DSN already has -- `has_table_privilege`/`pg_class`/`pg_roles` are all
    readable by any authenticated role, not just the table owner or a
    superuser (verified live against a real, non-superuser connection in
    this module's integration test)."""
    with engine.connect() as conn:
        owner_roles = _discover_owner_roles(conn)
        table_owners = _discover_fenced_tables(conn, owner_roles)
        leaks = _find_leaks(conn, table_owners)
        access_gaps = _find_access_gaps(conn, table_owners)
    return FenceCheckResult(
        fenced_tables=tuple(sorted(table_owners)),
        owner_roles=tuple(owner_roles),
        leaks=tuple(leaks),
        access_gaps=tuple(access_gaps),
    )
