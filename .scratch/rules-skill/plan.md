# Plan: the `rules` skill — Rules Database, file ⇄ DB migration, new sources, and their pipeline

## Context

Clean MDM's configuration has no home today. Each source's mapping (Dataset
Contract) and the merge rules (Mastering Policy) exist only as Python dicts
(`edgar_warehouse/mdm/clean/company_source.py`, `gleif_source.py`) plus one
JSON file (`edgar_warehouse/mdm/policies/company.json`). Nothing stores their
versions, proofs or approvals; `register_dataset`/`register_policy` have no
production caller; adding a source means writing Python. The Source Contract
work proved a config-file language on real data, but only as a throwaway
prototype (`.scratch/source-contract/prototype/`), and the Rules Database was
never designed past research (ticket 11).

The operator (2026-09-26) asked for one skill, owned and built by Claude, that
makes this easy: initialize the Rules Database, migrate rules between files and
the database, and add **any** new source end to end — identify and confirm the
source, profile and research its captured files, infer the MDM entities,
identifiers, fields and relationships, ask plain-language questions, then build
the parse configuration and merge rules and run the source's pipeline. Standing
direction: lean, clean, KISS; sources fully decoupled; new MDM fields easy to
add; remove a layer rather than tune it; no extra work.

## Decisions (operator, 2026-09-26)

| Topic | Decision |
|---|---|
| Owner | Claude builds the skill and simplifies the design (supersedes the Codex engine hand-off of 2026-09-21/22). |
| Storage | **Files in git + one table.** People and agents edit files (reviewed in PRs); `rules save` copies a file into the DB as a new version; the DB records status. (Changes ticket 06's "database is the master".) |
| Table | `rules.rule_version`: one row per version; content never changes; status only moves forward. |
| Migration | Two-way, generic: any file → DB, DB → files. |
| Start point | A source starts from bronze files already captured; capture stays separate. |
| Any source | Not tied to SEC. The skill identifies the source from its files and confirms it with the operator; if it cannot, it asks for the source's name. Research: sample files, this repo, the source's public web docs. The standing zero-SEC-requests rule still blocks `sec.gov` (data and docs). |
| Existing sources | SEC Company and GLEIF: move their MDM mapping and the Company merge rules into `rules/`; their parsing code stays. |
| One copy | Production code loads the `rules/` files; the Python/JSON copies are deleted. Live Company policy digest `983352e8…4049` must not change. |
| Pipeline | `rules run <source> --target mdm|silver --preview|--validate|--deploy`. MDM and silver run separately, MDM first, each from the same `read` section (ADR 0016). |
| Parsed data | Parse each run; no stored parsed-record table yet (recorded deviation from ADR 0016). |
| Silver output | Configurable, both available: `lakehouse` (Delta tables for Databricks) and `lakebase` (Postgres, as Databricks Lakebase). |
| Approval | **Anything that feeds MDM needs the operator's approval**: every merge-rules version and every source version with an `mdm` section. Silver-only versions do not. A fixed rule, never the agent's judgement. |
| Preview | Runs on a throwaway copy of the local MDM database (real matches: "joins existing Company", "new", "review"); falls back to an empty one. |
| Skill home | `skills/rules/` in the repo, symlinked into `~/.agents/skills/` (Claude, Codex, Grok). |
| Questions | Plain language, one at a time, each with a recommendation. A new MDM kind needs an operator ruling. |

## Design at a glance

**Files** (repo root, reviewed in PRs):
```
rules/
  outputs.yaml                     silver targets: lakehouse (Delta path, partitions), lakebase (DSN env name)
  merge/policy.yaml                Mastering Policy envelope: version, required_consumers, automatic_rules
  merge/<kind>.yaml                per-kind merge rules (company.yaml moved from edgar_warehouse/mdm/policies/company.json)
  merge/pending.yaml               declared-but-inactive rules (today's NAME_PROOFS)
  sources/<source>/source.yaml     source · bronze{family} · read · mdm{<source_code>: {table, contract}} · silver · tests · gate
  sources/<source>/fixtures/ , custom.py (optional)
```
`mdm.<source_code>.contract` is the existing Dataset Contract read by
`adapters.normalize` — no second mapping language. `mdm` maps from `read` rows,
not from silver (ADR 0016).

**Database** `rules` (own Postgres DB on the local server `edgartools-clean-mdm-pg16`; env `RULES_DATABASE_URL`), one table:
```
rules.rule_version(
  kind text CHECK (kind IN ('source','merge')), name text, version text,
  digest text  -- sha256 of body; CHECK digest = sha256(body)
  body text    -- canonical JSON text (store.canonical), stored as text so the DB can check the digest
  status text CHECK (status IN ('draft','proven','active','retired')),
  created_by text DEFAULT session_user, created_at timestamptz,
  proved_at timestamptz, proof jsonb, batch_hash text,
  approved_by text, approved_at timestamptz,
  activated_at timestamptz, retired_at timestamptz, clean_mdm jsonb,  -- what mdm_v2 recorded
  UNIQUE (kind, name, version))
UNIQUE INDEX one_active ON (kind, name) WHERE status = 'active'
```
Triggers: identity/body never change; status only moves forward; `approved_by
= session_user` and that login is in `rules_approver`; activation needs a proof,
and an approval whenever the version feeds MDM. Roles: a NOLOGIN owner, a
`rules_agent` login (what `RULES_DATABASE_URL` uses), one personal login per
approver. Column grants cover INSERT and UPDATE of the approval columns (the
agent cannot insert a pre-approved row). Tests connect as these logins, never
as a superuser.

**Commands** (`edgar-warehouse rules …`, registered like `register_mdm_subparser`, `edgar_warehouse/mdm/cli.py:25`; handlers import lazily):
`init` · `save` · `export` · `migrate --to-db|--to-files` · `status` · `profile <files>` · `check <source>` · `run <source> --target mdm|silver --preview|--validate|--deploy` · `approve` (operator's login) · `activate` · `adopt` · `retire`.

**Lifecycle**: save → draft; `run --validate` passes → proven; operator
`approve` (MDM-feeding versions) → `activate` registers into Clean MDM
(`register_dataset`/`register_policy`) and marks active, retiring the previous
one → `run --deploy` runs the Merge Stage / writes silver. Rollback = save the
old content under a new version label.

**Skill flow** (`skills/rules/SKILL.md`):
1. `init` / `migrate` modes wrap the commands.
2. `add <files>`: `rules profile` → identify the source (confirm, or ask its name) → research (this repo's `CONTEXT.md`, `evidence.KINDS`, existing mappings; the source's public docs; no sec.gov) → propose kinds, identifiers, fields, relationships → ask the operator one plain question at a time, each with a recommendation → write `source.yaml` + fixtures (+ merge rules) → `check` → `run --target mdm --preview` → `--validate` → ask for approval → `activate` → `--deploy`; then the same for `--target silver`.

## Mechanisms for the problems the design review found

- **Approval stamps inside the policy body** (`check_policy`, `activation.py:278-279, 438-443`): the row digest D is taken with the stamps null; `activate` fills them from `approved_by/approved_at` (pure function) to build the registered D′ and records both in `clean_mdm`; `export` writes D′ back. `save` refuses a file with filled stamps unless `mdm_v2` already holds that exact digest (an agent cannot type in its own approval).
- **Existing live versions** reach `active` through `rules adopt`, whose proof is parity with `mdm_v2` (policy digest present; `current_reading` equals the file's contract); no re-registration.
- **Parse-only changes** (ticket 11 research §7): for engine-parsed sources (those with a `read` section) activation stamps the Source Contract digest into the registered Dataset Contract, so a re-parse becomes a new reading instead of colliding on 031's unique key. Not applied to SEC Company/GLEIF (it would mint a new production reading).
- **Two databases, no shared transaction**: `activate` registers in Clean MDM first (idempotent; a rerun compares `current_reading` minus `registry_evidence`), then flips status in one rules-DB transaction. Only `activate` ever registers; `deploy` runs as the runtime role.
- **Identifiers**: LEI (mod-97), CUSIP, ISIN checked by check digit; CIK, CRD, EIN, ticker only by shape — the profiler ranks them as candidates, the operator confirms.

## Phases (one branch, worktree and PR each; P5 and P6 may run in parallel after P3)

**P1 — Rules files; production loads them; digests unchanged** (no DB, no new dependency)
- New `edgar_warehouse/rules/files.py`: strict PyYAML loader (JSON-typed scalars only; refuses duplicate and non-string keys; errors carry line numbers) and a writer that quotes any string that would read back as another type; `compose_policy()`, `load_source(name)`.
- New `rules/merge/{policy,company,pending}.yaml`, `rules/sources/sec.submissions.company/source.yaml`, `rules/sources/gleif/source.yaml`.
- `company_source.py` keeps its names (`CONTRACT`, `FIELDS`, `POLICY`, `PROOF`, `APPROVED_ACTIVATION`, `NAME_PROOFS`; ~15 test modules import them) but loads values from files; `gleif_source.dataset_contract` becomes a file read. Delete `edgar_warehouse/mdm/policies/` and its `pyproject.toml` include; add `COPY rules /app/rules` to `Dockerfile` and `Dockerfile.mdm-neo4j` (both copy only `edgar`, `edgar_warehouse` today); fix `tests/mdm/test_clean_company_source.py:418`.
- Tests: exact JSON→YAML→JSON round trip for every moved body; tricky scalars (`"1"`, `"010"`, `"2026-09-25T17:09:33Z"`, `"yes"`, `"null"`, `"1e5"`, `""`); `digest(POLICY) == 983352e8…`; each contract's digest equals its pre-move value; architecture test that the images copy `rules/`.

**P2 — Rules Database: `init`, `save`, `export`, `status`, `migrate`, `approve`, `retire`**
- `edgar_warehouse/rules/migrations/001_rule_version.sql` (checksum-applied like `store.migrate`), `db.py` (reuses `store.canonical`, `store.digest`), `cli.py`; extend `infra/scripts/provision-local-postgres-stores.sh` with the `rules` DB, roles and logins.
- Tests (throwaway PG16, as the real logins): every refusal — agent sets `approved_by` on insert or update; changed body; backward status; second active; same name+version with other content; DB digest = Python digest; files → DB → files byte-stable.

**P3 — Production engine from the prototype**
- Port `.scratch/source-contract/prototype/engine/source_engine.py` + `contract.schema.json` into `edgar_warehouse/rules/engine.py`: readers (json, jsonl, xml, csv, zip), primitives, `custom.py` API, checks, fixture tests, batch gate — only what the commands need (no mapdoc/lookups/SGML unless the trial needs them). New shape: `read` → rows; `mdm` → `normalize`; `silver` → types/keys. Add `rules check`.
- Tests: the prototype's gleif, form345, codex-fixture sources as fixtures, their named cases passing; import-boundary tests stay green; no sockets opened.

**P4 — `run --target mdm` (`--preview`, `--validate`, `--deploy`), `activate`, `adopt`**
- Parse bronze → `records.jsonl` + manifest → existing `execute_manifest` (`edgar_warehouse/mdm/clean/cli.py:252`), respecting its limits (≤1,000 records, 16 MiB, `record_count`). Preview: throwaway PG16 cloned from the local `mdm` DB when present (`pg_dump`/restore), `merge_harness.py`'s `Postgres`/`_fresh` lifted; nothing written to the real store. Validate: tests, checks, merge cases, gate on a pinned batch → `proven`. Activate needs the rules DB, the MDM governance-owner login and `CHANGE_LEDGER_DATABASE_URL` (registry authority; a new family first needs `mdm registry-open-draft` then activation).
- Tests: preview writes nothing; activate refused without approval; deploy refused for a non-active version; a parse-only change mints a new reading with no 031 collision; rerun after a registry version bump.

**P5 — Silver outputs**
- `edgar_warehouse/rules/silver.py`: typed pyarrow table → `lakehouse` (`deltalake` `write_deltalake` + `DeltaTable.merge` on key, `partition_by`) and/or `lakebase` (Postgres `INSERT … ON CONFLICT (key) DO UPDATE`); config `rules/outputs.yaml` + env overrides; lift `pg_type` from `infra/scripts/load_local_silver_landing.py` (`infra/` is not in the image).
- Tests: Delta merge idempotent on rerun; partition layout; Postgres upsert; a changed schema refused without a new version. Out of scope: Unity Catalog registration.

**P6 — `rules profile`**
- Streaming, bounded memory, reusing the engine readers: flattened paths, types, fill rate, distinct counts, samples, candidate keys, repeated groups (→ relationships), entity hints (organisation vs person name shapes), dates, addresses, cross-references, identifier candidates (check digits where they exist; `adapters.FORMATS` for CIK). JSON + a short plain summary.
- Tests: valid/invalid check digits; one fixture per format; memory bound on a large file.

**P7 — The skill and a cold trial**
- `skills/rules/SKILL.md` + `agents/openai.yaml` (layout of `~/.agents/skills/grilling/`), a symlink script into `~/.agents/skills/rules`.
- Test: every command the skill names exists in the parser.
- Acceptance: a fresh agent, given only the skill, onboards an unseen non-SEC source end to end locally (identify → profile → questions → files → preview → validate → approval → activate → deploy mdm, then silver) with no engine edits.

**New optional extra**: `rules = ["jsonschema", "deltalake"]` (PyYAML, pyarrow, sqlalchemy/psycopg2 already present); add to the CI `uv sync` lines.

## Records to amend (in the PR that makes each true)

- `docs/adr/0016…`: parse each run for now (P3/P4).
- `docs/specs/source-contract/spec.md` + `CONTEXT.md`: files are edited, the DB records; one `rule_version` table; `mdm` maps from `read` rows; approval for anything feeding MDM (supersedes ticket 06 option z); `run` modes (P2–P4).
- Ticket 11 (`claude/source-contract-11-rules-database-schema`): record the one-table decision; commit the research as its evidence.
- `CLAUDE.md` Quick Navigation: `rules/`, `edgar_warehouse/rules/`, the skill (P7).

## Working rules (every phase)

Branch `claude/rules-<phase>` fresh off `origin/main` in its own worktree;
`/gof-refactor-reviewer` before production code; checklist in the ticket with
ET times; three-axis `/code-review`; test every migration on a populated
store; zero SEC requests; `uv` only; CI green; merge only on the operator's
word for that PR. Ticket 17 (Company in one place) is separate and still
waits for the operator's review.

## Verification (end to end, after P7)

1. `edgar-warehouse rules init` on the local server → `rules.rule_version` exists; roles refuse an agent approval.
2. `rules migrate --to-db` → Company policy + SEC/GLEIF contracts saved; `rules adopt` → `active`, digest `983352e8…` matches `mdm_v2`; `rules migrate --to-files` → no diff.
3. Existing suites green: unit/architecture, `tests/mdm`, full Clean PG16 (`tests/integration/test_clean_*.py`).
4. Cold trial: a fresh agent runs `/rules add <files>` on an unseen non-SEC source → `source.yaml` written; `run --target mdm --preview` shows matches against a copy of local MDM; `--validate` → proven; operator `approve`; `activate` registers in `mdm_v2`; `--deploy` masters records; `run --target silver --deploy` writes Delta and Postgres; rerun changes nothing.
