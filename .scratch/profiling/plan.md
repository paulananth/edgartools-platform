# Plan: data-profiling and data-quality skills, RDM, and an agent context layer: generic, for agents

## Context

Today, data-onboarding takes **one feed whose kind is already known**. It profiles that feed by hand (`rules profile` is not built). It cannot take a whole data set and say what each part is: several files of different formats, or a set of database tables.

The operator wants a specialised **data-profiling** skill. Given any data set, it finds:
- master data;
- reference data;
- relationships;
- transaction data;
- metadata.

It documents hierarchies, finds data quality issues, specifies silver tables, and suggests a store. Its findings feed data-onboarding, which calls it.

Everything is designed for agents: MDM, RDM, relationships and silver are their context.

**Genericity rule (operator, 2026-10-04).** Nothing is pinned on SEC, Company, Person or any existing source. They are only examples and test data:
- skills, scripts, views, commands and specs work for any domain, kind, identifier and relationship type;
- a lint test fails if skill or spec files name a specific source, kind or identifier outside a marked "Examples" section;
- two trials prove it: one on the SEC and GLEIF captures, and one on a non-SEC public data set.

What exists today:
- **MDM:**
  - kinds are listed in `KINDS` (`edgar_warehouse/mdm/clean/evidence.py:10`);
  - merge rules exist for 2 kinds;
  - relationships have contract syntax (`skills/data-onboarding/REFERENCE.md` `relationships:`) and typed `CONTRACTS` in `mdm/clean/relationships.py`, and are stored as `mdm.current_record` rows.
- **Reference data:** one YAML file under `rules/reference/`, read by `rules_files.reference()` and the `in_reference@1` check. It is embedded in the Mastering Policy and is not defined in `CONTEXT.md`.
- **Data quality:**
  - there is no separate skill;
  - it is data-onboarding's **quality** step and refining-rules' **change-quality** step, both writing `rules/sources/<source>/quality.yaml`.
- **Inputs:** the source engine reads xml, json, jsonl and csv (plus one zip member). It cannot read Parquet or databases.
- **Not built:**
  - key or foreign-key discovery;
  - a cross-reference table;
  - a general silver writer (rules-skill ticket 05);
  - an agent context interface.

## Decisions (operator, 2026-10-04)

**data-profiling**

1. A new specialised skill. Finding the data types is the top priority. Its store suggestion is advisory only.
2. **Inputs.** It accepts:
   - files: XML, CSV, JSON, JSONL, Parquet, zip;
   - database tables: through a read-only URL held in an environment variable (never printed), or as exported files.
3. **Engine.** Transient DuckDB (`uv run --with duckdb`), never a platform dependency. Snowflake is profiled in place with SQL.
4. **Five classes:** master data, reference data, relationship, transaction/event data, metadata/other. Each carries evidence and confidence.
5. **New domains.** When master data fits no existing kind, profiling suggests a domain name and a kind, explains why it is master data, and asks for approval.
6. **Keys.**
   - Profiling finds each part's unique identifier from the data alone. If there is none, it designs a key (a natural composite, or a surrogate with its rule) for approval.
   - The key becomes the source's **record key**.
   - Other identifiers are proposed for the **MDM cross-reference table**: lookup only, never used to join.
   - Identifier shapes are found by generic detectors: fixed length or pattern, character classes, and check-digit families (mod 97, Luhn, mod 10/11). Known identifier types are examples, not rules.
7. **Completeness.**
   - Below 5 GB, every test is a full scan.
   - Above 5 GB, profiling samples, then runs full passes on its candidates.
   - It states the time before any long pass.
8. **Sensitive data.** Fields are tagged personal, sensitive personal or none, and their samples are masked. Sensitive personal = GDPR Article 9 categories, government-issued personal IDs, and financial account and card numbers (operator, 2026-10-05).
9. **Time.** For each part, profiling reports: snapshot or changes only, date roles, versions per key and refresh rate. Where the data needs it, it designs an **as of** and **as at** time and a known time series.
10. **Parseable first, never guess.** Nested lists become child tables. A finding without evidence is reported as "unknown". Unstructured content is listed, then handled under decision 31.
11. **Hierarchies are inferred separately for each source.** Four kinds of evidence count:
    - parent columns and self-links;
    - functional dependencies;
    - exact code nesting;
    - separate level tables.

    Each **reference hierarchy** is documented as a record:
    - its levels, with names and samples;
    - the rule that proved it, and its evidence;
    - its depth, orphans, shape (balanced or ragged) and valid dates.

    Stewards name the levels and add definitions in a workbook sheet. A near-exact hierarchy is accepted. Its invalid rows are marked, a data quality check is specified for them, and each gets a proposed fix or augmentation with evidence; a fix with no evidence is marked "needs steward". **Master data hierarchies** are MDM relationships, a separate concept.
12. **Relationships.** For each relationship, profiling decides whether it is onboarded together with its master or separately, and writes down why.
13. **Silver.** For every part MDM does not own (transaction/event data and published reference data), profiling writes a full table spec:
    - name, grain, columns with types and nullability;
    - key, links to masters (source key plus MDM id, with overlap %);
    - as-of and as-at columns, partitioning, load mode;
    - why.
14. **Outputs.** `REPORT.md` for the operator, and `findings.yaml` for agents. The operator approves the classification and designed keys, and their exact words and the time are recorded. A `compare` mode reports drift on a new delivery.

**data-quality**

15. A new `skills/data-quality/` is extracted from data-onboarding's **quality** step and refining-rules' **change-quality** step, and both skills call it.
    - It turns profiling's defects into checks and fixes, and marks invalid rows with proposed fixes.
    - Once approved, its checks run on every load.

**Wiring**

16. data-onboarding always calls profiling first, unless approved, current findings exist. It then plans one onboarding per part, in dependency order: reference data, then master kinds with their "together" relationships, then transaction data and "separate" relationships.
17. data-onboarding prefills its steps from the findings. It asks only what profiling cannot know: the mapping to MDM fields, which source wins a field, and the `on_fail` setting for each check.
18. refining-rules runs `compare` before changing a live feed. Drift items become proposed changes.

**RDM**

19. RDM is its own domain, kept separate from MDM in concept. Reference data gives values their meaning.
    - Its system of record is its own Postgres database, `rdm`, holding code sets, codes (label, definition, synonyms, valid dates), reference hierarchies, crosswalks, and versions (draft, approved, published).
    - Published versions go to silver. MDM pins a version and its hash.
20. The existing reference YAML migrates into RDM as its first code set, and MDM's policy pins the version. This is its own ticket.
21. **Hierarchy storage.** The default is one parent link per node, plus a generated readable path, level and depth. The research note compares this with a closure table, ltree and nested sets, and checks which extensions Snowflake-hosted Postgres offers. The RDM spec decides on that evidence.

**Agents**

22. Everything is designed for agents. The interface is KISS: no MCP and no new server.
    - Generic, self-describing read-only views carry `COMMENT ON` text on every column:
      - `mdm.entity_context` (any kind);
      - `mdm.relationship_context` (any type);
      - `rdm.code_context` (any code set);
      - the silver specs.
    - One bundle command reads them: `edgar-warehouse context <kind|code_set> <key|--search words> [--as-of] [--hops N]`. It returns bounded JSON (at most 8 KB) with definition, path, version, valid dates and provenance.
23. Search uses labels and synonyms with plain Postgres text search, falling back to `ILIKE`. There are no embeddings.
24. Agents write drafts only. The operator's recorded approval publishes them.
25. **No graph database.** Relationships stay in MDM Postgres. Parent chains use recursive SQL with a hop limit.

**Matching and extraction**

26. **Name-based matching for any master kind that carries names, gated by proof.**
    - Each rule pairs a normalized name with supporting attributes that profiling chooses for that kind.
    - Approval needs at least 600 labelled pairs per rule, with the 95% lower confidence bound on precision at least 99.5% (operator, 2026-10-05). Recall is reported.
    - A match below the bar goes to the steward review queue.
    - The rules are written in refining-rules.
27. **Unstructured extraction is accepted only when it is certain.** A value counts only if a deterministic parser read it from a structure (an HTML table, an iXBRL tag, a labelled section), or if it is cross-checked against structured data or a second, independent extraction. Everything else stays "candidate, unconfirmed", with its location, and never merges. The order is HTML and iXBRL first, then PDF and free text.

**Proof and controls**

28. **Trial A** uses the SEC and GLEIF captures with a known answer key. **Trial B** uses a non-SEC public data set (a relational sample with customers, products, orders, a category hierarchy and code lists, as CSV files and as a SQLite or Postgres database), with an answer key written by hand first. Both trials must pass with no domain-specific change.
29. **The recreation proof** regenerates today's MDM, RDM and relationships with the skills, in a sandbox, then writes a diff.
    - It uses full local copies of today's 3 sources, plus every other captured feed sliced to one coherent cohort: 500 fixed entities and 2 years, with the list stored in the repo. All copies are local; no live requests to any provider.
    - Recorded rulings are replayed, marked "replayed", and valid only in the sandbox.
    - The result is a `DIFF.md` where every difference is matched or explained.
30. **Missing pieces are built before the proof** (see Build order).
31. **Checkpoints.** The operator approves the research note and specs, each `findings.yaml`, each rule and code-set version by its digest with its evidence, and each merge.
32. **Parallel work.** At most 2 Claude worktrees, only where rows are independent.
33. **Budget.**
    - The $100 of cloud credits goes only to cold trials and the proof, each estimated first, with work stopping at $80 spent to report to the operator.
    - At this account's limit, a handoff note goes in the ticket so the operator can resume from the second account.

## Flow

```
any data set (files | tables) ─► DATA-PROFILING ─► REPORT.md + findings.yaml (approved)
                                                         │
                   DATA-ONBOARDING: discover (calls profiling) → plan parts (dependency order)
          ┌───────────────┬──────────────────┬──────────────────┬──────────────────┐
          ▼               ▼                  ▼                  ▼                  ▼
   reference → RDM   master kind →      transaction →     DATA-QUALITY        new domain /
   (code sets,       rules + MDM        SILVER spec →     (checks, invalid     designed key /
    hierarchies,     (+ "together"      Bookkeeping       rows, fixes; every   cross-ref ids
    crosswalks)       relationships)    (+ "separate"     load)                → operator
          │                ▲             relationships)
          ├─ pinned version┘
          └─ published ─► silver
agents read everything through: edgar-warehouse context  (views over MDM, RDM, silver)
live feed, new delivery ─► REFINING-RULES ─► compare (profiling) ─► proposed changes
```

## Build order

Each row is its own ticket, branch, worktree and PR. Each gets a GoF consult before code, a three-axis `/code-review`, CI green, and a merge only on the operator's word.

| # | Ticket | Done test |
|---|---|---|
| 0 | **Ownership PR** (`AGENTS.md`, `CLAUDE.md`) and `scripts/dev/overlap_guard.sh` | The operator approves the ownership section. The guard stops a test commit that touches a file in an open Codex PR. |
| 1 | **Research note** (`.scratch/profiling/research/01-classify-and-profile.md`, primary sources): class definitions (DAMA-DMBOK, ISO 8000); profiling metrics; unique column combinations and inclusion dependencies (SPIDER, BINDER, Metanome); key design; time models; sensitive-data detection; drift; generic identifier detectors; RDM practice (ISO/IEC 11179, SKOS); hierarchy storage for agents; agent context design; unstructured extraction; store heuristics; Snowflake-hosted Postgres features (ltree, pg_trgm, full-text search) | The operator approves it. Every claim has a cited source. |
| 1a | **Specs**: `docs/specs/rdm/spec.md`, `docs/specs/agent-context/spec.md`, the silver table spec format, and the `findings.yaml` schema. New `CONTEXT.md` terms: Reference Data, Code Set, Crosswalk, Reference Hierarchy, Master Data Hierarchy, Transaction Data | The operator approves them. |
| 1b | **data-profiling skill**: `skills/data-profiling/` with modes inventory → profile → keys → links → classify → quality → suggest-store → report → approve, plus compare; tested DuckDB helpers; `link.sh`; data-onboarding gains discover and plan-parts and drops its by-hand profile; refining-rules gains compare; the genericity lint test | Trial A matches its answer key. Trial B matches its answer key with no domain-specific change. `doctor` reports 0 unresolved references. The lint passes. |
| 1c | **data-quality skill**, extracted and called by onboarding and refining-rules | Both trials' defects become checks that load, and invalid rows are marked with evidence-backed fixes. |
| 2 | **RDM database**, publishing to silver, the MDM version pin, and migrating the existing reference YAML | A fresh `rdm` database migrates from zero. A code set with its crosswalk and hierarchy publishes to silver. MDM pins it, and today's mastering counts are unchanged. |
| 3 | **MDM cross-reference table** and its contract syntax | Identifiers from a contract are written and read back, and never join records. |
| 4 | **`mdm.relationship_context`** and relationship onboarding for any typed relationship | Trial relationships come back with roles and dates. A recursive parent chain matches the source's own data. |
| 5 | **Agent context views** and the `edgar-warehouse context` command | For any kind, code set and relationship, lookup, `--search`, `--as-of` and `--hops` each return JSON of at most 8 KB with definition, path, version and provenance. |
| 6 | **Silver writer** (ticket 05), driven by profiling's silver specs | A spec lands typed rows, each with its source key and MDM id. |
| 7 | **Readers and custom parsing steps** for each captured feed with no reader, ordered by the findings | Each passes its tests on the cohort and reaches onboarding's test step. |
| 7b | **Name-based matching** | Each rule's 95% lower confidence bound on precision is at least 99.5%, on at least 600 labelled pairs. Matches below the bar are queued for stewards. |
| 7c | **Unstructured extraction** | Only deterministic or cross-checked values are accepted. Unconfirmed candidates keep their location and never merge. |
| 8 | **Recreation proof** | Every line of `DIFF.md` is matched or explained, and the operator accepts it. **This ends the program.** |

These rows may run side by side, at most 2 at a time: in phase A, 1c with 3, and 4 with 7b; in phase B, 2 with 6. The order of the rows within each phase follows "Coordination with Codex".

## Gap rulings (2026-10-04)

34. **Labelling.** For each name rule, an agent pre-labels the pairs using only certain evidence, such as a shared issued identifier or cross-reference id. Pairs it cannot settle go to the operator, and the operator spot-checks 50 of the agent's labels. If any spot-check label is wrong, the whole set is relabelled.
35. **Trial B's data set is Contoso V2** (MIT), chosen by the operator 2026-10-05 from the research note's candidates. Its answer key is written before the skill sees it.
36. **Silver for the trials and the proof** is a `silver` schema in a disposable local PG16. The writer goes through one small sink interface, so a Snowflake sink can follow as its own ticket. The spec format does not depend on the store.
37. **Production hosting and deployment** are a separate, later program with its own map. This program ends at the accepted local recreation proof.
38. **Row 7's size** is set after row 1b. Profiling's inventory lists each captured feed with no reader, and each one becomes a checklist part in the row 7 ticket, with its own branch and PR.

## Tickets and time

There is one map, `.scratch/profiling/map.md`, with **one ticket per build row: about 13 tickets** (1, 1a, 1b, 1c, 2–6, 7, 7b, 7c, 8). The tickets are required by CLAUDE.md's checklist rule, and each is the handoff point between sessions and accounts.

Rows 7 and 7c each keep one ticket, with one checklist part per feed or per format. Each feed or format still gets its own branch and PR.

Rough working time, not counting the wait for the operator's approvals:

| Row | Estimate |
|---|---|
| 1 Research note | 1–2 days |
| 1a Specs | 1–2 days |
| 1b Profiling skill, plus trials A and B | 4–6 days |
| 1c Data-quality skill | 1–2 days |
| 2 RDM | 3–5 days |
| 3 Cross-reference table | 2–3 days |
| 4 Relationships | 3–5 days |
| 5 Context | 2–3 days |
| 6 Silver writer | 3–5 days |
| 7 Readers | 2–4 days per feed; at about 6–10 feeds, 3–6 weeks |
| 7b Name matching | 3–5 days, plus labelling |
| 7c Unstructured extraction | 2–4 weeks |
| 8 Recreation proof | 3–5 days |

The total is about 3–5 months. Rows 7 and 7c carry the most uncertainty, and each estimate is revised once row 1b's inventory is known.

## Coordination with Codex (operator, 2026-10-04: "Claude waits for Codex")

Codex is working toward full old-parser retirement: configured reading in `crates/source-contract`, `rules/sources/**`, `edgar_warehouse/workers/source_*.py`, the data-platform skill's READING and COMBINING pages, and `tests/engine/test_data_skill_bundle_postgres.py`. It merged #815 and #817–#821, and #822 is open as a draft. Its remaining scope is:
- producer provenance;
- the census, ticker and cascade integration;
- GLEIF streaming;
- configured acquisition;
- adapter replacement;
- full installed replay;
- deleting the old parser.

**Phase A: start now, no overlap.**
- Row 0 (ownership PR and overlap guard), first of all.
- Row 1 (research note).
- Row 1a (specs). The RDM spec must reconcile with #815: the reference tables embedded in each contract become a pinned RDM snapshot (version plus hash) inside the contract. No reader changes.
- Row 1b: the new `skills/data-profiling/` folder, its helpers, the lint test, and trials A and B.
- Row 1c: the new `skills/data-quality/` folder.
- Row 3 (cross-reference table).
- Row 4 (relationship view).
- Row 5, for MDM and relationships only.
- Row 7b (name matching).

**Edits to existing skills wait for a clear moment.** This covers the onboarding and refining-rules wiring, moving the quality steps out, and one line in data-platform/SKILL.md. Before each such edit, Claude checks Codex's open PRs and worktrees (`gh pr list`, `git worktree list`). If any Codex PR or worktree touches the same file, the edit waits until that work merges.

**Phase B: starts after Codex's old-parser retirement goal is merged.**
- Row 2 (RDM, and migrating the embedded reference tables).
- Row 5, for RDM.
- Row 6 (silver writer).
- Row 7 (readers).
- Row 7c (unstructured extraction).
- Row 8 (recreation proof).

Phase B starts by re-reading main to absorb Codex's final design, and re-checking each phase B row against it.

**Conflict prevention: all three protections (operator, 2026-10-04).**

1. **Ownership, written down first.** A small PR adds an ownership section to `AGENTS.md`, which Codex reads, and to `CLAUDE.md`. The operator approves it before any other commit.
   - **Claude's paths in this program:**
     - `skills/data-profiling/**`, `skills/data-quality/**`;
     - `docs/specs/rdm/**`, `docs/specs/agent-context/**`;
     - `.scratch/profiling/**`;
     - the new MDM migrations for cross-reference and context views;
     - the `context` command module.
   - **Codex's paths:**
     - `crates/source-contract/**`, `rules/sources/**`;
     - `edgar_warehouse/workers/source_*.py`;
     - `skills/data-platform/{READING,COMBINING}.md`;
     - `tests/engine/test_data_skill_bundle_postgres.py`.
   - **Shared files are changed only after a check:** the onboarding and refining-rules skills, `data-platform/SKILL.md`, `CONTEXT.md`, and `edgar_warehouse/cli.py`. See the guard in item 2.
2. **Overlap guard.** `scripts/dev/overlap_guard.sh` runs before every commit and every push. It lists the files the branch changed and compares them with:
   - the files of every open Codex or Grok PR (`gh pr view --json files`);
   - the dirty and unmerged files in every Codex or Grok worktree.

   Any overlap stops the work and goes to the operator.
3. **Git and CI.** Each branch is rebased onto main before review, and nothing merges without CI green.

**Before every ticket:** run `git branch --show-current`, `git status`, `gh pr list` and `git worktree list`. If a Codex or Grok file overlaps, stop and ask. Codex and Grok work is never edited.

## Tracking

- `.scratch/profiling/map.md` holds one ticket per row. Each ticket keeps a checklist, with each part stamped in ET (`TZ=America/New_York date`).
- A status line follows each merge: done, next, blocked.
- Any part blocked by the agent limit is marked "blocked: agent limit, resets <ET>", with a handoff note.

## Verification

- Each row's done test, above.
- Affected tests are run locally with testmon, and CI runs everything.
- Throwaway containers are removed after each run.
- Both trials and the proof are recorded under `.scratch/profiling/trials/`.

## Out of scope

- An MCP server, or any new agent server.
- A graph database.
- Embeddings and vector search.
- Any change to production stores, and any prod hosting or deployment (a separate later program). Profiling never reads prod S3.
- Replacing today's MDM with the recreated one. The recreation is a proof only.
- Approving, activating or merging anything for the operator.
