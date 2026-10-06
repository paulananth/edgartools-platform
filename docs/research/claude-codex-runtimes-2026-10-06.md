# What Claude and Codex are doing

Read on 2026-10-06 from `origin/main` at `a9aaac91` (PR #837). This note separates the two runtimes. Later role skills quote it instead of restating the history.

Path ownership is the table in `AGENTS.md` and `CLAUDE.md`, added by Claude in PR #823 (`259f954c`, profiling 00). A shared path (`skills/data-onboarding/**`, `skills/refining-rules/**`, `skills/data-platform/SKILL.md`, `CONTEXT.md`, `edgar_warehouse/cli.py`, `AGENTS.md`, `CLAUDE.md`) is edited only after `scripts/dev/overlap_guard.sh` passes.

## Claude: profiling, data quality, and agent context

Claude owns `skills/data-profiling/**`, `skills/data-quality/**`, `docs/specs/rdm/**`, `docs/specs/agent-context/**`, `.scratch/profiling/**`, the MDM cross-reference migration and context views, the `context` command, and `scripts/dev/overlap_guard.sh`.

Merged on `main`, in order:

| PR | Commit | What landed |
|---|---|---|
| #824 | `e9c0032b` | Research note: classify, profile, RDM, and agent context (profiling 01) |
| #825 | `571ab11f` | Specs (profiling 01a): `docs/specs/rdm/spec.md`, `docs/specs/agent-context/spec.md`, `docs/specs/profiling/findings.md`. Each spec is still marked draft for operator approval |
| #831 | `d4f7fe36` | `skills/data-profiling/` (profiling 01b). It reads local copies and writes `REPORT.md` and `findings.yaml`. It does not change a store, a rule, or a source |
| #832 | `6742bc54` | `skills/data-quality/` (profiling 01c). It turns profiling defects into engine checks and writes `rules/sources/<source>/quality.yaml` only after the operator decides each check |
| #835 | `c170c534` | MDM cross-reference ids are kept for lookup and are never used to join (profiling 03) |
| #836 | `5b410e24` | Relationship types as data, `mdm.relationship_context`, and the parent chain (profiling 04) |
| #837 | `a9aaac91` | `edgar-warehouse context` and `mdm.entity_context` (profiling 05), in `edgar_warehouse/context.py` |

`docs/specs/agent-context/spec.md` also names `rdm.code_context` and `silver.table_context`. The command module says those two views join the command in a later phase. They are not what `edgar-warehouse context` reads today.

`CONTEXT.md` is the MDM language those specs sit on: Company, Person, and Security are separate identities; a cross-reference is not a join key; similar names do not merge Companies. Profiles (Adviser, Audit Firm, Fund) hang on an identity and are not identities.

Claude's name-matching trial is not on this branch. The worktree `edgartools-platform-claude-profiling-07b` is on `claude/profiling-07b-name-matching` and holds that work. Do not treat it as a decision.

## Codex: configured reading and the source contract

Codex owns `crates/source-contract/**`, `rules/sources/**`, `edgar_warehouse/workers/source_*.py`, `skills/data-platform/READING.md`, `skills/data-platform/COMBINING.md`, and `tests/engine/test_data_skill_bundle_postgres.py`.

That work is the configured engine: a captured file is read by a pinned contract, then combined and prepared by workers. The engine code is the `source-contract` crate. The worker entry points on `main` include `edgar_warehouse/workers/source_read.py`, `source_combine.py`, `source_readings.py`, and `source_stream.py`.

Merged reading work already on `main` includes:

| PR | Commit | What landed |
|---|---|---|
| #819 | `473f78e6` | `source.combine` for keyed collections and joins. The contract shape is `skills/data-platform/COMBINING.md` |
| #821 | `21a1a885` | Company main documents through configured source orchestration |
| #826 | `5169930c` | Company ticker catalogs read with header-driven matrix rules |
| #827 | `389a020e` | The custom ticker catalog parser replaced by configured iteration |
| #828 | `42d7bb2d` | Unused submission loaders retired; Company document assertions qualified |
| #829 | `e5918e64` | Bounded native JSON streaming and authenticated snapshots |
| #830 | `bc146cd4` | Authenticated reading partitions consumed by combining and MDM preparation |
| #833 | `337e737e` | Framed JSON projected natively, with publication record counts pinned |

`skills/data-platform/READING.md` is the grammar for those contracts. Its qualification boundary is still open: Company catalog and census joins, full Company mastering, and active GLEIF archive and XML retirement are not done. A passing primitive test is not that proof. `skills/data-platform/SKILL.md` is the shared package index (setup, parse, master, custom step). It is not Codex-only, and these role skills do not rewrite it.

Open and not merged: PR #834, branch `codex/configured-xml-framing-20261006`, "Wire bounded configured XML reading through native projection". It edits `crates/source-contract/**`, `edgar_warehouse/workers/source_stream.py`, `rules/sources/gleif/level1-json.yaml`, `skills/data-platform/READING.md`, and `tests/engine/test_data_skill_bundle_postgres.py`. Leave that branch alone.

## Where the three roles stop

- Data modeling decides structure in the words `CONTEXT.md` and the profiling specs already use. It does not profile bytes and it does not write a `source.yaml`.
- The data engineer moves captured files through workers and commands that already exist. It does not extend `crates/source-contract`.
- The data scientist measures and reports evidence. It does not approve a rule or activate a source version.

The procedures for those jobs already live in `skills/data-profiling`, `skills/data-quality`, `skills/data-onboarding`, `skills/data-platform`, `skills/refining-rules`, `skills/bookkeeping`, and `skills/change-journal`. The role skills point at those files.
