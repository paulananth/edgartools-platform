# Agent context: MDM, RDM, relationships and silver, for agents

Status: draft for operator approval (profiling ticket 01a). Research:
`.scratch/profiling/research/01-classify-and-profile.md` section 10. Plan
decisions 22–25.

## 1. Purpose

Agents are the main users of master data, reference data, relationships and
silver. They need small, self-explaining answers they can trust, through what
already exists: Postgres views and the `edgar-warehouse` command bundle. There
is no MCP server, no new service, no graph database and no embeddings.

Everything here is generic: any kind, any code set, any relationship type.
Kinds and codes named below are examples only.

## 2. Views (read only)

Each view and each of its columns has a `COMMENT ON` in plain English. Ticket
05 tests that column comments on views read back through `col_description`.

| View | Database | One row per | Columns |
|---|---|---|---|
| `mdm.entity_context` | MDM | live master entity (any kind) | `entity_id`, `kind`, `name` (the surviving name), `status`, `canonical_id`, `identifiers` (jsonb: namespace → values, from the record and the cross-reference table), `fields` (jsonb: surviving values, each with its winning source), `sources` (jsonb: source code → record keys), `valid_from`, `valid_to`, `batch_id`, `published_at` |
| `mdm.relationship_context` | MDM | live relationship (any type) | `relationship_id`, `type`, `from_entity_id`, `from_kind`, `from_name`, `to_entity_id`, `to_kind`, `to_name`, `role`, `valid_from`, `valid_to`, `source_code`, `record_key`, `batch_id` |
| `rdm.code_context` | RDM | code in the published version of each code set | `code_set`, `code`, `label`, `definition`, `synonyms`, `path`, `label_path`, `level`, `depth`, `version`, `sha256`, `valid_from`, `valid_to`, `status` |
| `silver.table_context` | silver | silver table | `table_name`, `grain`, `key`, `links` (column → master kind), `time_columns`, `load_mode`, `definition`, `spec_ref` |

`mdm.entity_context` is built on the existing `mdm.current_entity` view, so it
covers every kind through one shape. A kind-specific table (such as today's
`mdm.company`) feeds it through `current_entity`; agents never read
kind-specific tables.

As-of reads use the same views with a time argument (`--as-of`): for MDM, the
record versions valid at that instant; for RDM, the version published at that
instant.

## 3. The command

```
edgar-warehouse context <kind|code_set|relationship|silver> <key>
edgar-warehouse context <kind|code_set> --search "<words>" [--limit 5]
    [--as-of <ISO time>] [--hops N] [--detail brief|full] [--page <token>]
```

- `<kind>` is any MDM kind: `<key>` is an entity id, or `<namespace>:<value>`
  for an identifier. `<code_set>` takes a code. `relationship <entity_id>`
  lists that entity's relationships, following up to `--hops` (default 1,
  maximum 3) with recursive SQL. `silver <table>` returns a table's spec.
- `--search` matches labels, synonyms and names: Postgres full-text search
  (`websearch_to_tsquery`, `simple` configuration for codes) ranked with
  `ts_rank_cd`, then `pg_trgm` similarity for near misses. Returns the top
  matches with their path or kind so the agent picks one. A search with no
  match is logged (`context-search-miss`), which is how embeddings would be
  reconsidered later.
- It reads with read-only logins from the existing environment variables. It
  never prints a database address or a secret.

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
lookup, `--search`, `--as-of` and `--hops` each return valid JSON of at most
8 KB with definition, path (codes), version and provenance; a missing key
returns an actionable error; no output contains a database address.
