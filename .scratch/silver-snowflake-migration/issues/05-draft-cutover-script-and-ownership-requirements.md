# Draft the Cutover Script and Ownership Requirements

Type: task
Status: claimed
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
