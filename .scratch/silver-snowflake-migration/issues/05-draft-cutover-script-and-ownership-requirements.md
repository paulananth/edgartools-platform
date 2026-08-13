# Draft the Cutover Script and Ownership Requirements

Type: task
Status: resolved
Blocked by: none

## Question

Write a committed, re-runnable checklist/script skeleton (mirroring
`infra/snowflake/sql/bootstrap/09_mdm_mirror_schema.sql` and
`infra/scripts/generate_mdm_mirror_ddl.py`'s already-working pattern) that
this migration's eventual implementation must follow, operationalizing the
map's standing requirement: every provisioning step is committed and
re-runnable, and ownership goes to one dedicated loader role from day one.

Name the specific prior incidents this exists to prevent, so the checklist
reads as evidenced requirements, not generic caution: the MDM Snowflake
mirror schema silently lost because it was provisioned by an uncommitted
manual session (CLAUDE.md, "MDM Snowflake mirror schema lost on cutover");
a `GRANT OWNERSHIP ... REVOKE CURRENT GRANTS` step that separately stripped
an unrelated role's `SELECT` grants (CLAUDE.md, "Manifest-pipeline
ownership + cursor-syntax incident"). Include: which role owns the new
landing-zone schema and silver dbt models, what grants downstream
consumers (gold's dbt run, MDM's readers, the dashboard) need and how they
survive a future re-application of this migration's own scripts, and
whether `COPY CURRENT GRANTS` (the fix the MDM incident settled on) is the
right default here too.

Unblocked — can start immediately, independent of the architecture
decisions in Tickets 01-04.

## Answer

Written as real, tested, committed artifacts — not prose describing what a
future script should do — matching the two named precedents exactly.

### Ownership decisions

1. **The new landing-zone schema and silver dbt models are owned by
   `EDGARTOOLS_PROD_LOADER`** — the platform's existing single dedicated
   pipeline-object owner (already holds gold's 20 dynamic tables, the MDM
   mirror's 19 tables, and the graph schema). Not a new role: minting one
   would repeat the exact ownership fragmentation the loader-role policy
   was created to eliminate (CLAUDE.md, "Manifest-pipeline ownership +
   cursor-syntax incident"). Bonus, not the reason: since `profiles.yml`'s
   prod dbt target already defaults to this role, gold's `ref()` into
   silver (Ticket 03) needs zero new grants — owner-level access is
   implicit.
2. **MDM's new silver-reader role (Ticket 03) is brand new and
   minimally-scoped**: `EDGARTOOLS_PROD_MDM_SILVER_READER`, matching the
   `EDGARTOOLS_GRAPH_REVIEW_READER` precedent — a dedicated per-consumer
   reader, not an extension of MDM's existing write role. One operational
   detail this ticket does **not** decide, flagged explicitly rather than
   silently assumed (see the script's own trailing comment): whether
   MDM's read session activates this role via a separate credential
   (cleanest separation) or as a secondary role on the existing loader
   credential (reuses today's shared-secret pattern, partially reintroduces
   the overlap the dedicated role was chosen to avoid). Resolved when
   MDM's actual read code is implemented, not here.
3. **`COPY CURRENT GRANTS` doesn't apply here** — it's a mitigation for
   `GRANT OWNERSHIP ... REVOKE CURRENT GRANTS` transferring ownership of an
   *existing* object with pre-existing grants (the exact MDM incident this
   ticket is named after). Every object here is newly created (`CREATE ...
   IF NOT EXISTS`), so there's nothing to preserve — the applicable lesson
   from that incident is the broader one already applied throughout: never
   use `GRANT OWNERSHIP ... REVOKE CURRENT GRANTS` at all, only additive,
   idempotent statements.
4. **Grants are narrower than the MDM mirror's**, a deliberate access-control
   decision, not an oversight: landing gets `SELECT, INSERT` only (no
   `UPDATE`/`DELETE` — append-only by design, per Ticket 01/02); MDM's
   reader gets `SELECT` only, `FUTURE`-scoped rather than a hand-maintained
   per-table list, directly closing the exact drift gap that caused the
   `INSTITUTIONAL_HOLDS`/`EMPLOYED_BY` incidents.

### Committed artifacts

- **`infra/scripts/generate_silver_landing_ddl.py`** — a real,
  tested generator, mirroring `generate_mdm_mirror_ddl.py`'s anti-drift
  guarantee through a different mechanism suited to what actually exists:
  since `silver_store.py`'s `_DDL` is a raw DuckDB SQL string, not
  SQLAlchemy ORM metadata, this generator executes it in an in-memory
  DuckDB connection and reflects columns/types back out via DuckDB's own
  `information_schema`, rather than hand-transcribing column lists that
  could silently drift. Verified live against the real `silver_store.py`:
  reflects all 30 landing-eligible tables (the 31
  `PROTECTED_TABLE_REGISTRY` tables minus `pipeline_run_lease` — a real bug
  caught while building this, see below) with correct DuckDB→Snowflake type
  mapping (`TEXT`→`TEXT`, `TIMESTAMP WITH TIME ZONE`→`TIMESTAMP_TZ`,
  `JSON`→`VARIANT`, `DECIMAL(p,s)`→`NUMBER(p,s)`, etc.), a shared row-level
  `parse_sequence` `SEQUENCE` per Ticket 02's decision, and
  `SELECT, INSERT`-only grants to `EDGARTOOLS_PROD_LOADER`.
- **`infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql`** — the
  committed, readable snapshot of that generator's real output (schema
  `EDGARTOOLS_SILVER_LANDING`, matching `EDGARTOOLS_SOURCE`/
  `EDGARTOOLS_GOLD`'s full-prefixed naming convention, not `MDM`'s shorter
  unprefixed form), confirmed byte-for-byte identical to a fresh
  regeneration except for the hand-authored preamble (same relationship
  `09_mdm_mirror_schema.sql` has to its own generator).
- **`infra/snowflake/sql/bootstrap/12_silver_schema_and_mdm_reader.sql`** —
  hand-authored, not generated, because `EDGARTOOLS_SILVER`'s tables are
  new dbt models with no prior Python definition to reflect from (`dbt run`
  creates them, not this script). Provisions only what must exist first:
  the empty schema, `CREATE DYNAMIC TABLE`/`CREATE TABLE`/`CREATE VIEW` on
  it for the loader role (the same real "`CREATE SCHEMA IF NOT EXISTS`
  evaluates the privilege before checking existence" gotcha CLAUDE.md's MDM
  mirror follow-up already documented, applying here too), and the MDM
  reader role with `FUTURE`-scoped `SELECT`.

### Real bug caught while drafting this, not merely a documentation exercise

`pipeline_run_lease` is dual-listed in `PROTECTED_TABLE_REGISTRY` (needed
to survive the *old* whole-file candidate/canonical merge, per
`silver_protection.py`'s own comment) but is cross-execution lease state
(`sec_fetch_active`), not domain data — it isn't append-only (a lease's
whole point is a mutable current status) and stays exactly where it is
today, unaffected by this migration. A naive "generate DDL for everything
in `PROTECTED_TABLE_REGISTRY`" approach would have silently landed it in
the append-only zone, which is structurally wrong for what it is. Caught
by testing the generator against the real registry rather than trusting
the table list at a glance, and now excluded explicitly (`_EXCLUDED_FROM_LANDING`),
not by omission — so a future re-run can't silently reintroduce it if the
registry changes.

### This closes the map's frontier

All six tickets on this map are now resolved. Implementation is a separate
follow-up pass, per the map's own decision-spec-only mode — these two SQL
files are the first two real steps of it, provisioned before any other
implementation work begins, so the "every provisioning step is committed
and re-runnable" requirement this ticket exists to operationalize is true
from day one rather than retrofitted later.
