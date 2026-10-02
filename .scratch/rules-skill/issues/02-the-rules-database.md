# The Rules Database

Type: task
Status: resolved: the Rules Database and `rules init/save/approve/activate` exist on main (rules skill 14, #757; Fresh Rules authority, #738) (2026-10-02 audit, mastering to-do 01).
Was: open
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

## Found by ticket 01's review (decide here)

- **files → DB → files is not byte-stable today.** The 5 rules files carry
  30 comment lines (operator decisions and approval notes), and
  `store.canonical` sorts keys. With the comments removed, `dumps(load(f))`
  gives back each file exactly, but the canonical-JSON body loses both the
  comments and the key order. Choose one: keep the file text in the row
  beside the canonical body, drop the comments, or define "no diff" as
  "equal digests".
- **The reverse of `files.policy()`.** `export` / `migrate --to-files` must
  split `kinds` back into one file per kind. Put that next to `policy()` in
  `edgar_warehouse/rules/files.py`, so the file layout lives in one module,
  and test it as `policy()` → write → `policy()`.
- `gleif_source.dataset_contract` changes the dict that `files.source()`
  returns. This is safe because `source()` reads the file again on each call.
  If a cache is added, copy the value first.
