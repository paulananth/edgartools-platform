# Agent context: MDM, RDM, relationships and silver, for agents

Status: approved by the operator ("approved and already merged 825", 2026-10-05); MDM part built in ticket 05 (#837), RDM part in ticket 05's RDM part. Research:
`.scratch/profiling/research/01-classify-and-profile.md` section 10. Plan
decisions 22–25.

## 1. Purpose

Agents are the main users of master data, reference data, relationships and
silver. They need small, self-explaining answers they can trust, through what
already exists: Postgres views and the `edgar-warehouse` command bundle. There
is no MCP server, no new service, no graph database and no embeddings.

Everything here is generic: any kind, any code set, any relationship type.
Specific kinds, codes and tables appear only in the Examples section.

## 2. Views (read only)

Each view and each of its columns has a `COMMENT ON` in plain English. Ticket
05 tests that column comments on views read back through `col_description`.

| View | Database | One row per | Columns |
|---|---|---|---|
| `mdm.entity_context` | MDM | live master entity (any kind) | `entity_id`, `kind`, `name` (the surviving name), `status`, `canonical_id`, `identifiers` (jsonb: namespace → values that decide identity), `cross_references` (jsonb: namespace → values its records carry, lookup only, kept apart so an agent never reads one as identity), `fields` (jsonb: surviving values, each with its winning source), `sources` (jsonb: source code → record keys), `valid_from`, `valid_to`, `batch_id`, `published_at` |
| `mdm.relationship_context` | MDM | period of a live relationship (any type) | `relationship_id`, `type`, `from_entity_id`, `from_kind`, `from_name`, `to_entity_id`, `to_kind`, `to_name`, `role`, `scope`, `derived`, `period`, `valid_from`, `valid_to`, `valid_from_basis`, `valid_to_basis`, `last_seen`, `sources` (jsonb: each source code and record key that states it), `batch_id` |
| `rdm.code_context` | RDM | code of every version ever published (current, superseded or retired) | `code_set`, `code_set_name`, `code`, `label`, `definition`, `synonyms`, `path`, `label_path`, `level`, `depth`, `parent_code`, `crosswalk`, `version`, `sha256`, `valid_from`, `valid_to` (the version's), `version_status`, `code_status`, `code_valid_from`, `code_valid_to` (the code's business dates), `invalid_reason`, `approved_by`, `approved_at`, `published_at` |
| `silver.table_context` | silver | silver table | `table_name`, `grain`, `key`, `links` (column → master kind), `time_columns`, `load_mode`, `definition`, `spec_ref` |

**How `mdm.relationship_context` reads a relationship (ticket 04, built 2026-10-06).**
- One row per period: a relationship held, left and held again has two rows,
  each with its own `valid_from` and `valid_to`.
- `role` is a person's capacity in the link (director, owner); it is empty for
  other links. `scope` is the family the source states it in.
- A link MDM calculates (an ultimate parent walked from the stated parents) has
  `derived` true and basis `calculated`, and one row per stretch of time its
  chain held (accounting-chain-v2). Under an earlier policy (v1) it is one row
  with no dates.
- `valid_from_basis` and `valid_to_basis` say where a date came from: stated
  (the source gave it, such as a corporate action's effective date) or
  observed (first seen). `ended_by` names the succession (e.g.
  `SUCCESSOR_ENTITY`) whose date ended a period.
- Retired links are left out. A link can be stated by several records, so the
  stating records are a list (`sources`), not one source code and record key.
- What a type means (the kinds at its ends, whether it is a hierarchy) is in
  the Mastering Policy's relationship types (`rules/merge/relationships.yaml`);
  the view names no type.
- `mdm.relationship_chain(entity, type, max_hops, at)` walks one entity's
  parents through one type within one scope, nearest first, with the links
  that hold at `at` (business time; now by default), up to `max_hops` (at most
  50, for checks; the command's `--hops` stays at most 3). A link back to an
  entity already on the chain ends it, marked `cycle`.
- The command's relationship walk (ticket 05) goes both ways (parents and
  children) with one query per hop through the link-start and link-end
  indexes, up to `--hops` 3 and at most 1,000 links, and says so when it stops.
  `--as-of` picks the links that hold at a business time. `--as-at` (a past
  recording) reads `mdm.relationship_version` (profiling ticket 05b): every
  recorded state of every relationship, one row per change, written by a
  trigger on `mdm.current_record`; the walk takes the versions open at the
  generation `--as-at` picks, through their start and end indexes, and keeps
  the links that held at that time. Names are as MDM holds them now.

**Where MDM context comes from (checked against the schema, 2026-10-05).**
- MDM keeps history for every kind already: each committed batch stores its
  projections in `mdm.batch.effects` with its `generation` and `created_at`.
  A kind with its own versioned table (with `valid_from`, `valid_to`,
  `from_generation`, `to_generation`) is read from that table instead.
- The existing reader `ContractReader` (`edgar_warehouse/mdm/clean/consumer.py`)
  already rebuilds an entity at any generation, follows `canonical_id`, and
  returns `field_provenance` (each field's winning source). The command reads
  every entity lookup through it (at the generation `--as-at` or `--as-of`
  picks, or the latest). `mdm.entity_context` is SQL over the current state;
  its `fields` (value and winning source), `name` and `identifiers` come from
  the same entity body, and a test holds the view equal to the reader at the
  latest generation. Search reads the view's tables, never the reader.
- What each kind and relationship type means is data, in
  `rules/context/definitions.yaml`, outside the Mastering Policy (an edit is a
  reviewed PR, not a new policy version). A test fails until a new kind or
  type has its line.
- `valid_from` / `valid_to` for a kind without its own versioned table are the
  `created_at` of the batch that introduced the projection and of the batch that
  replaced it.

**Time.** Two times are kept apart (plan decision 9):
- `--as-at <time>`: what MDM had recorded by then. The command takes the
  highest `generation` whose batch `created_at` is at or before that time.
- `--as-of <time>`: what was true in the business at that time. MDM masters
  with an `as_of` per batch (`effects->>'as_of'`); the command takes the latest
  generation whose `as_of` is at or before that time. RDM uses the version whose
  `valid_from`..`valid_to` covers it, for both flags; `--as-at` shows that
  version as it stood then (not yet replaced or retired), and `--as-of` also
  checks the code's own business dates (`code_valid_from`..`code_valid_to`).

## 3. The command

```
edgar-warehouse context <kind|code_set|relationship|silver> <key>
edgar-warehouse context <kind|code_set> --search "<words>" [--limit 5]
    [--as-of <ISO time>] [--as-at <ISO time>] [--hops N] [--detail brief|full] [--page <token>]
```

- `<kind>` is any MDM kind: `<key>` is an entity id, or `<namespace>:<value>`
  for an identifier. `<code_set>` takes a code. `relationship <entity_id>`
  lists that entity's relationships, following up to `--hops` (default 1,
  maximum 3), one query per hop. `silver <table>` returns a table's spec.
- `--search` matches labels, synonyms and names: Postgres full-text search
  (`websearch_to_tsquery`, `simple` configuration for codes) ranked with
  `ts_rank_cd`; when that finds nothing, names containing the words as typed
  (`ILIKE`, plan decision 23; no extension needed). MDM names are searched by
  `mdm.entity_search`, which uses a word index on each name. Returns the top
  matches with their path or kind so the agent picks one. A search with no
  match is logged (`context-search-miss`), which is how embeddings would be
  reconsidered later.
- It reads through the existing environment variables (`MDM_DATABASE_URL`),
  as the application role, which may only read tables, and in read-only
  transactions. A subject that is no master kind and not `relationship` is a
  code set, read from RDM through `RDM_DATABASE_URL` (its restricted runtime
  login), also in read-only transactions. It never prints a database address or a secret: a driver
  error is reported by its type only.

### 3.1 The answer (JSON, at most 8 KB)

```json
{
  "kind": "<kind>", "key": "<key>", "name": "<name first>",
  "definition": "<plain words>",
  "fields": {"<field>": {"value": "...", "source": "<source code>"}},
  "path": "<label path, for codes>",
  "trust": {"source": "...", "version": "...", "sha256": "...",
            "valid_from": "...", "valid_to": null, "status": "published",
            "approved_by": "...", "approved_at": "...", "as_of": "..."},
  "related": [{"type": "...", "name": "...", "key": "..."}],
  "truncated": false, "next_page": null,
  "next_step": "<what an agent can do next, e.g. the command for more>"
}
```

- Names come first; ids appear beside names, never alone.
- **An MDM entity answer, as built (ticket 05):** `name`, `kind`, `key`,
  `entity_id`, `status`, `definition`; `fields` as a list of
  `{field, value, source}` (with `record_key` and `effective_at` under
  `--detail full`), sorted by field, so it pages like any list; `identifiers`
  and `cross_references` apart; `sources` (source codes, or each with its
  record keys under full); `trust` (`generation`, `recorded_at`, `as_of`,
  `policy_digest`, `run_id`, `status`); the first 10 `related` links with
  `related_count`; and `merged_from` when the key named an entity merged into
  another. A relationship answer lists `related` links (`depth`, `type`, `from`
  and `to` each named, `role` for a person's capacity, `derived`) with each
  type's `definitions`, and under `--detail full` each link's stating records
  (`sources`). A search answer lists `matches`
  (`name`, `kind`, `entity_id`, `status`, `matched_by`). Search and
  relationship answers carry `trust` for MDM's latest generation; an entity
  read `--as-at` or `--as-of` says which parts are current
  (`trust.current_parts`).
- **A code answer, as built (ticket 05, RDM part):** `name` (the label),
  `kind` `code`, `code_set`, `key`, `definition`, `code_set_definition`,
  `path` (the label path), `path_codes`, `level`, `depth`, `parent_code`,
  `code_status`, `code_valid_from`, `code_valid_to`, `synonyms` (the first 20, with `synonyms_count` when more), `crosswalk` (the codes of other sets it maps to, with
  match types), `meaning` (the version's meaning hints), and `trust`
  (`version`, `sha256`, `valid_from`, `valid_to`, the version's `status`,
  `approved_by`, `approved_at`). `--as-of` reads the version valid then;
  `--as-at` the newest published by then. `rdm.code_context` holds every code
  of every version ever published; `rdm.code_search` searches one
  version's labels and synonyms (full-text, then `ILIKE`, with `%` and `_`
  matching themselves); with `--as-of` or `--as-at` it searches the version of
  that time. A search answer lists `matches` (`name`, `code`, `path`,
  `matched_by`) and carries the same `trust`. `--detail full` adds the code
  set's `used_in` (where its values live); `--hops` and `--type` are refused
  for a code set. A code set's id never takes a kind's name or
  `relationship`, which the command reads from MDM.
- One list per answer pages: `fields`, `related`, `matches` or `crosswalk`. A string over
  1,000 characters is clipped, and the answer says `clipped`.
- Over 8 KB, the answer is cut at a whole list item, `truncated` is true and
  `next_page` gives the token.
- An error says what was wrong and the exact command that would work.

## 4. Writing

Agents never write through `context`. Drafts are written by the skills
(profiling, data-quality, refining-rules) into each store's draft state:
RDM draft versions, rules files in a PR, MDM steward review. Only the
operator's recorded approval publishes.

## 5. How the skills use it

- data-profiling: looks up existing kinds, code sets and identifiers before
  proposing a new one.
- data-onboarding and refining-rules: read the context of a kind or code set
  before mapping, and cite it in their questions.
- data-quality: reads code sets to propose fixes for invalid rows.

## 6. Done test (plan row 5)

For any kind, code set, relationship and silver table in the trial stores:
lookup, `--search`, `--as-of`, `--as-at` and `--hops` each return valid JSON of at most
8 KB with definition, path (codes), version and provenance; a missing key
returns an actionable error; no output contains a database address.

## Examples

Examples only; nothing above depends on them.

- `edgar-warehouse context company cik:0000320193` (a kind and an identifier).
- `edgar-warehouse context us_state DE`, `--search "state banks"` (a code set).
- Today's company-specific table `mdm.company` feeds `mdm.current_entity`, which
  is why `entity_context` reads through the reader, not kind tables.
