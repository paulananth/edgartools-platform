# 05 Agent context views and command

Type: task. Phase: A (MDM) / B (RDM). Blocked by: 03, 04 (02 for RDM). Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [x] GoF consult (ContractReader, the mdm CLI, store migrations): leave all as is; register `context` like the other domains from `cli.py`, imports inside the handler; search never goes through the reader's per-field provenance queries 2026-10-06 08:35 ET
- [x] Definitions as data: `rules/context/definitions.yaml` (each kind and relationship type in plain words), outside `rules/merge/` so the Mastering Policy digest stays 1e38238f…03da4; a test that every kind and every relationship type has one (added 2026-10-06 08:35 ET) (`rules/context/definitions.yaml`; `tests/mdm/test_context.py` checks every kind, the schema's kind list and every type; the policy pins are unchanged) 2026-10-06 08:50 ET
- [x] Migration 007: `mdm.entity_context` (one row per live master entity, aliases and merged entities left out) with `COMMENT ON` for the view and every column; `cross_references` kept apart from `identifiers` (lookup only); a GIN index on `stage_record` identifiers for `<namespace>:<value>` lookup of any namespace; name search indexes on entity rows and on the company table (`007_entity_context.sql`; PG16 tests) 2026-10-06 08:50 ET
- [x] `MIGRATIONS` and `RUNTIME_FUNCTIONS` updated; a populated store at 006 takes 007 and keeps its rows (`entity_search` granted; the 005-to-006 test now drops 007 too) 2026-10-06 08:50 ET
- [x] `col_description` test over every column of every context view (006's included) (entity_context, relationship_context, cross_reference) 2026-10-06 08:50 ET
- [x] The view equals the reader: fields and winning sources of `mdm.entity_context` equal `ContractReader.entity()` at the latest generation (PG16 test) 2026-10-06 08:50 ET
- [x] `edgar-warehouse context <kind> <entity id | namespace:value>`: name first, definition, fields with winning source, identifiers, cross-references, trust (policy digest, generation, as of, recorded at), first related links; `--detail brief|full` (PG16 tests; the GLEIF slice) 2026-10-06 08:50 ET
- [x] `--search "<words>"`: full-text search on names (`websearch_to_tsquery`, `simple`), ranked; `ILIKE` when it finds nothing (plan decision 23; no extension); a miss is logged `context-search-miss` (`mdm.entity_search`; PG16 test covers words, contains, miss) 2026-10-06 08:50 ET
- [x] `--as-at` (what MDM had recorded then: the generation committed by that time) and `--as-of` (business time: the generation whose as-of is at or before it), both read through `ContractReader.entity(generation=)` (PG16 test with two batches; the GLEIF slice 60/60 each) 2026-10-06 08:50 ET
- [x] `edgar-warehouse context relationship <entity>`: links in both directions, `--hops` 1–3, one bounded query per hop through the link-start and link-end indexes, `--as-of` through `relationship_holds`, `--type` filter, walk cut at a fixed number of links and said so (PG16 tests; 60 links paged; the GLEIF slice 180 walks) 2026-10-06 08:50 ET
- [x] Answers at most 8 KB in UTF-8 bytes: one pageable list per answer, cut at a whole item, `truncated`, `next_page`, `next_step` (unit test with 2-byte characters; 480 real answers, largest 8,151 bytes) 2026-10-06 08:50 ET
- [x] Read only: each connection is `READ ONLY`; an error says what was wrong and the command that would work; no output holds a database address or password (a test with a fake URL) (fake-URL test: no login, password, host or database name in either stream; `MDM_DATABASE_URL` unset says what to set) 2026-10-06 08:50 ET
- [x] Spec updated where the build differs: cross-references apart from identifiers; ILIKE in place of pg_trgm; relationships `--as-at`; the walk is per-hop queries, the parent chain recursive SQL (`docs/specs/agent-context/spec.md` §2, §3, §3.1) 2026-10-06 08:50 ET
- [x] Skills point at it: data-onboarding REFERENCE.md "Reading MDM's context" (shared by onboarding and refining-rules), data-profiling's kinds step; doctor 0 unresolved, genericity lint passes 2026-10-06 08:50 ET
- [ ] ~~Pointers in data-onboarding and refining-rules SKILL.md~~ deferred: the guard flags both files in the stale Codex worktree codex/bundled-data-guidance-20261004; the operator's "Proceed: it's stale" was for ticket 01c, so they wait; REFERENCE.md carries the guidance (added 2026-10-06 08:50 ET)
- [ ] ~~data-quality reads code sets~~ moved to phase B with `rdm.code_context` (added 2026-10-06 08:50 ET)
- [x] Trial check on the ticket 04 slice (real GLEIF entities): lookup, search, as-at, as-of, hops each under 8 KB (`.scratch/profiling/trials/context/RESULT.md`) 2026-10-06 08:50 ET
- [ ] `rdm.code_context` (phase B)
- [ ] `silver.table_context` (phase B, with ticket 06)
- [x] Three-axis review applied: a page with no item that fits is an error, not a page pointing at itself; search pages with `--page`; error commands are whole commands, with search words shell-quoted; search and relationship answers carry `trust` (latest generation, recorded time, policy digest); `--detail full` links carry their stating records (one query); an `--as-at`/`--as-of` entity answer says cross-references and source records are current; the "names no kind" claim names the company table; the view-equals-reader test also compares name and identifiers. Not applied: the Standards "missing subject index" (stage_record.subject is indexed by its UNIQUE constraint, stage_record_subject_key); GoF's dispatch dict and one next-page helper, as the first commit of phase B (unit, PG16 tests: 68 passed) 2026-10-06 13:53 ET
- [ ] ~~Relationships `--as-at`~~ deferred to a relationship-versioning ticket (map fog): it needs a versioned relationship table or an index into the batch history (added 2026-10-06 13:53 ET)
- [ ] `mdm migrate` for 005, 006 and 007 and an MDM image rebuild: not run on deploy; `MDM_DATABASE_URL` not set here and no container runtime (added 2026-10-06 13:53 ET)
- [x] CI found the data skill bundle could not import the new module (its wheel lists modules one by one): `edgar_warehouse/context.py` added to `packages/data-skill/pyproject.toml` 2026-10-06 14:15 ET
- [x] PR, CI, merge: PR #837, all six checks green after the bundle fix; merged on the operator's "Merge" (squash a9aaac91) 2026-10-06 14:32 ET

## Decisions

- Relationships `--as-at` (a past generation) is not built here: no index finds one entity's links in the batch history, and a scan of every batch per hop is unmeasured. The command answers with an error that names `--as-of` (business time, which does work) and the `mdm.relationship_context` view. A versioned relationship table would make it cheap; follow-up. (2026-10-06 08:35 ET)
