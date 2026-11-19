# The Gold writer role applied, and the operator's decisions of this turn

Status: open
Type: task

## Parts

- [x] Operator, 2026-11-19 14:41 ET, to the list of pending approvals: "Applying the Gold writer role. Approve". Applied: role `EDGARTOOLS_GOLD_WRITER` (USAGE on the warehouse and `DB_EDGARTOOLS_GOLD`, USAGE and CREATE VIEW on `DB_EDGARTOOLS_GOLD.GOLD`), a key-pair service user of the same name, the key-pair-only authentication policy. Created by an account owner's SQL (the ANANP11 connection, on the operator's approval of the apply, which I had said an account owner performs); the same objects as `infra/terraform/access/snowflake` (PR 1927). No mirror database is granted yet (`mirror_databases` is empty).
- [x] Proved by connecting with the key pair: identity `EDGARTOOLS_GOLD_WRITER`; a view created and dropped in `GOLD`; refused: a view in `PUBLIC`, a table in `GOLD`, an account-usage read. 2026-11-19 14:41 ET
- [x] The private key and the dbt settings are in `~/.config/edgartools/gold-writer/` (mode 0600, never printed).
- [ ] `terraform import` of the role, user, grants and policy attachment before the first apply of `accounts/prod` (the SQL and the code are the same objects)
- [ ] Grant the writer USAGE, schema USAGE and SELECT on each mirror database when the mirrors exist: put the three names in `mirror_databases` and apply
- [x] Operator, 2026-11-19 14:41 ET: the priced mirror create plans are approved when presented, once the load has finished and the sizes are final (no answer was given to that item now); the refresh interval "no": no choice from the operator, so the plan keeps its proposal of 60 minutes; the `snowflake_admin` password rotation "no stop asking": not raised again.
- [x] Learning → skill: aws-snowflake-operations, "Access identities" (the Gold writer, its file, how to prove it, importing SQL-made objects into Terraform). 2026-11-19 14:41 ET
