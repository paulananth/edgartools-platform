# The Rules Database

Type: task
Status: open
Blocked by: 01

## Outcome

A `rules` Postgres database with one table, `rules.rule_version`, and the
commands `init`, `save`, `export`, `status`, `migrate --to-db|--to-files`,
`approve` and `retire`. The body never changes; status only moves forward;
one active version per name; only a person's own login can approve. Design:
[plan.md](../plan.md), "Design at a glance".

## Checklist (times ET)

- [ ] `/gof-refactor-reviewer` before code.
- [ ] Migration `001_rule_version.sql`, applied with a checksum, like
  `store.migrate`.
- [ ] Roles: a NOLOGIN owner, a `rules_agent` login and approver logins;
  column grants on INSERT and UPDATE. Extend
  `infra/scripts/provision-local-postgres-stores.sh`.
- [ ] Commands under `edgar-warehouse rules …`.
- [ ] Tests on a throwaway PG16, connecting as the real logins: every refusal;
  the DB digest equals the Python digest; files → DB → files is byte-stable.
- [ ] Three-axis `/code-review`, then PR and CI.
