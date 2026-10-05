# Reference Data Management (RDM)

Status: draft for operator approval (profiling ticket 01a). Research:
`.scratch/profiling/research/01-classify-and-profile.md` sections 8, 9 and 13.
Plan decisions 19–21, 24.

## 1. What RDM is

Reference data gives values their meaning. A code means nothing until a code
set says what it stands for (see Examples). RDM keeps those
code sets, apart from master data in concept:

| | Master data (MDM) | Reference data (RDM) |
|---|---|---|
| Describes | things: entities with identity and a lifecycle | the meaning of values used to describe things |
| Size | grows with the business | small, near-constant between versions |
| Changes by | new and changed records, merged by rules | a new version of the whole code set, approved |
| Hierarchy | a **Master Data Hierarchy** is a set of MDM relationships | a **Reference Hierarchy** groups codes inside one code set |

RDM is generic: it holds any code set from any source. Specific code sets
appear only in the Examples section.

## 2. The model

```
code_set ─< code_set_version ─< code (one parent_code per hierarchy)
                │                 └─< code_label (synonyms, per language)
                ├─< level (named hierarchy levels)
                └─< crosswalk_row  (this version's code → another version's code, match type)
approval: on each version (draft → approved → published), with the approver's words and time
```

### 2.1 Tables (`rdm` database, schema `rdm`)

Every table and column carries a plain-English `COMMENT ON` (who writes it, who
reads it, why it exists).

| Table | Key | Columns |
|---|---|---|
| `code_set` | `code_set` | `name`, `definition`, `authority` (who issues the codes: a standard body, a source, or internal), `steward` |
| `code_set_version` | (`code_set`, `version`) | `status` (`draft`, `approved`, `published`, `retired`), `valid_from`, `valid_to`, `supersedes`, `created_by` (agent or person), `evidence` (jsonb: profiling findings ref, counts), `approved_by`, `approved_words`, `approved_at`, `published_at`, `sha256` (of the canonical form, §4) |
| `code` | (`code_set`, `version`, `code`) | `label`, `definition`, `parent_code` (nullable; one hierarchy per code set version), `valid_from`, `valid_to`, `status` (`valid`, `invalid`), `invalid_reason` |
| `code_label` | (`code_set`, `version`, `code`, `language`, `label`) | `kind` (`preferred`, `synonym`), `source` (steward, profiling, agent draft) |
| `level` | (`code_set`, `version`, `depth`) | `name`, `definition` (stewards name the levels) |
| `code_path` | (`code_set`, `version`, `code`) | `path` (text, delimiter-escaped codes, root first), `label_path` ("Finance > Depository > State banks"), `level`, `depth`. **Written once at publish**; never edited |
| `crosswalk_row` | (`from_set`, `from_version`, `from_code`, `to_set`, `to_version`, `to_code`) | `match_type` (`exact`, `close`, `broad`, `narrow`; SKOS mapping), `evidence` |

Integrity:
- `parent_code` references a `code` in the same version (foreign key); a
  publish refuses a cycle (recursive check with `CYCLE`).
- Rows of a version are immutable once its status is `published`: a trigger
  refuses any update or delete; a change is a new version that `supersedes` it.
- One `published` version per code set at any instant: `EXCLUDE USING gist
  (code_set WITH =, tstzrange(valid_from, valid_to) WITH &&) WHERE (status =
  'published')`, with `btree_gist`.

### 2.2 Hierarchy storage

- Drafts hold one `parent_code` per code: the only thing an editor changes.
- Publishing computes `code_path` (`path`, `label_path`, `level`, `depth`)
  with one recursive query and stores it on the immutable version. A Postgres
  generated column cannot do this (it cannot read other rows).
- Subtree lookup: `path LIKE '<prefix>/%'` with a `text_pattern_ops` index.
- `ltree` is optional, an index only, inside RDM. The published format never
  depends on it.

## 3. Lifecycle and approval

| Step | Who | What happens |
|---|---|---|
| draft | an agent (profiling, data-quality, refining-rules) or a steward | creates a `draft` version: codes, labels, levels, crosswalks, invalid-row fixes, with `evidence` and `created_by` |
| review | the operator or a steward | reads the draft through `edgar-warehouse context` and the version diff (§5) |
| approve | the operator only | records exact words and time (`approved_by`, `approved_words`, `approved_at`). Agents never approve |
| publish | a command, after approval | computes `code_path` and `sha256`, sets `published`, closes the previous version's `valid_to`, writes the silver copy (§6) |
| retire | the operator | sets `retired`; nothing deletes a published version |

Hierarchy exceptions (plan decision 11): a near-exact hierarchy is accepted;
its violating codes are kept with `status = invalid` and an `invalid_reason`,
and a data quality check is proposed for them. A proposed fix needs evidence;
without it, the code is marked "needs steward".

## 4. Canonical form and the pin

The canonical form of a version is UTF-8 JSON Lines, sorted by code, one object
per code with `code`, `label`, `parent_code`, `valid_from`, `valid_to`,
`status`, and its labels sorted. `sha256` is taken over those bytes.

A consumer pins `{code_set, version, sha256}`:

- **MDM's Mastering Policy** pins each code set it uses instead of embedding a
  YAML copy (`rules/reference/*.yaml` today). A new version still needs the
  policy's approval, as today.
- **Source contracts** (PR #815, `crates/source-contract/src/reference.rs`)
  keep embedding reference rows, within their bounds (≤ 16 tables, ≤ 10,000
  rows per table, ≤ 100,000 cells). RDM publishes the embeddable mapping plus
  its pin, so the contract embeds the rows **and** `{code_set, version,
  sha256}`. The reader does not change. A code set above those bounds needs a
  pin by reference resolved from silver at load: a later reader change, Codex's
  area, in phase B.

## 5. Agent access

Read: `rdm.code_context` (agent-context spec) through `edgar-warehouse context
<code_set> <code>` and `--search`. Each answer carries the definition, the
`label_path`, the version, `sha256`, the valid dates and the status.

Write: agents create drafts only (`created_by` names the agent and skill).
Publishing and approval are the operator's. A version diff
(`edgar-warehouse rdm diff <code_set> <from> <to>`, built in plan row 2) lists
added, removed, relabelled and moved codes.

## 6. Publishing to silver

Each publish writes the version to silver as three tables keyed by
(`code_set`, `version`): `rdm_code` (with `path`, `label_path`, `level`,
`depth`), `rdm_code_label`, `rdm_crosswalk`. The silver writer is plan row 6;
until it exists, the publish writes the same rows as canonical JSON Lines files
beside the version for consumers to load.

## 7. Migration of the existing reference YAML (plan row 2)

- Each `rules/reference/<name>.yaml` becomes a code set version, with any
  standard codes it carries as crosswalk rows (see Examples).
- The Mastering Policy switches from embedding the YAML to pinning the version;
  `in_reference@1` reads the pinned version. The YAML is removed only after a
  run shows the same mastering counts with the pin.
- Contract-embedded tables (PR #815) gaining the pin beside their rows is a
  **handoff request to Codex** in phase B: `rules/sources/**` and
  `crates/source-contract/**` are Codex's paths (AGENTS.md, path ownership).
  RDM only publishes the embeddable mapping and its pin.

## 8. Not in this spec

Hosting RDM in production, and its deployment (a later program). A user
interface for stewards beyond the workbook sheet profiling generates.

## 9. Settled here

- `rdm` is its own database in the same Postgres server as `rules`,
  `bookkeeping` and `change_journal` (operator: "Own RDM database").
- Every published version is kept; retired versions are never deleted, so any
  pin stays resolvable.

## Examples

Examples only; nothing above depends on them.

- Codes needing a code set: `DE` (a state), `10-K` (a form type), `6022` (an
  industry code).
- A reference hierarchy: industry division → major group → industry.
- The existing `rules/reference/sec-place-codes.yaml` becomes the first code set
  in plan row 2; its ISO 3166 codes become `exact` crosswalk rows.
