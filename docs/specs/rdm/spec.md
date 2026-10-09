# Reference Data Management (RDM)

Status: approved by the operator ("approved and already merged 825", 2026-10-05); built in profiling ticket 02. Research:
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
| `crosswalk_row` | (`from_set`, `from_version`, `from_code`, `to_set`, `to_version`, `to_code`) | `match_type` (`exact`, `close`, `broad`, `narrow`; SKOS mapping), `evidence`. `to_version` is `outside` for a code set RDM does not hold (an outside standard) |
| `code_set_usage` | (`code_set`, `version`, `store`, `object`, `field`) | `store` (`mdm`, `silver`, `source`, `other`), `match` (`exact`, `upper_trimmed`), `note`: where the codes' values live and how to compare them |
| `code_set_hint` | (`code_set`, `version`, `kind`, `ordinal`) | `kind` (`meaning`, `use_when`, `avoid_when`, `example_question`), `text`: hints for an agent in plain words |

The last two are the semantic layer an agent reads before using a code set
(operator, 2026-10-07: "make rdm be friendly to agents need semantic layer
hints"). They are frozen with the version, like its codes, but are not in the
canonical form: a consumer's values do not depend on them.
`edgar-warehouse rdm describe <code_set>` returns them with the definition,
the version and its pin, counts, the code sets it maps to and a few codes,
in at most 8 KB.

Integrity:
- `parent_code` references a `code` in the same version (foreign key); a
  publish refuses a cycle or a missing parent (it walks each code's parents
  before writing any path).
- Rows of a version are immutable once its status is `published`: a trigger
  refuses any update or delete; a change is a new version that `supersedes` it.
- One `published` version per code set at any instant: a unique index on
  the code set over published versions whose `valid_to` is empty, and
  publishing closes the replaced version's `valid_to` at the new one's
  `valid_from` (operator, 2026-10-07: chosen over the `btree_gist`
  exclusion constraint, which not every PG16 build ships).
- A version's content changes only while it is a draft; approval needs the
  approver's name and exact words; nothing deletes a version.

### 2.2 Hierarchy storage

- Drafts hold one `parent_code` per code: the only thing an editor changes.
- Publishing computes `code_path` (`path`, `label_path`, `level`, `depth`)
  by walking each code's parents, and stores it on the immutable version. A Postgres
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
| retire | the operator | sets `retired` and closes `valid_to`; nothing deletes a published version |
| verify | anyone | `rdm verify` recomputes a version's sha256 from its rows and compares it with the stored one |

A published version must name, in `supersedes`, the newest version ever
published (current or retired); the first names none. The database checks
this too. Publishing writes the files (§6) before it commits.

The agent records the operator's approval in their name and exact words, as
the Rules agent does (operator, 2026-09-29, rules skill ticket 14); the
database refuses an approval without both, or by the version's own drafter.
Agents never approve on their own words.

Hierarchy exceptions (plan decision 11): a near-exact hierarchy is accepted;
its violating codes are kept with `status = invalid` and an `invalid_reason`,
and a data quality check is proposed for them. A proposed fix needs evidence;
without it, the code is marked "needs steward".

## 4. Canonical form and the pin

The canonical form of a version is UTF-8 JSON Lines, sorted by code, one object
per code with `code`, `label`, `definition`, `parent_code`, `valid_from`,
`valid_to`, `status`, `invalid_reason`, the name of its `level`, its labels
sorted and its crosswalk rows sorted. `sha256` is taken over those bytes, so a pin covers everything a
consumer reads (a changed crosswalk is a new sha256).

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

Commands (`edgar-warehouse rdm`, JSON out): `init` and `migrate` (the schema
owner, `RDM_MIGRATION_DATABASE_URL`); `list`, `describe`, `draft --file`,
`import-reference`, `approve`, `publish --out`, `retire`, `verify` and `diff` (the runtime
login, `RDM_DATABASE_URL`). Lookup and search of codes are
`rdm.code_context` and `edgar-warehouse context` (agent-context spec, profiling
ticket 05, RDM part).

## 6. Publishing to silver

Each publish writes the version to silver as three tables keyed by
(`code_set`, `version`): `rdm_code` (with `path`, `label_path`, `level`,
`depth`), `rdm_code_label`, `rdm_crosswalk`. The publish writes these rows as
canonical JSON Lines files beside the version: `<out>/<code_set>/<version>/`
holds `canonical.jsonl` (the pinned bytes), `rdm_code.jsonl`,
`rdm_code_label.jsonl`, `rdm_crosswalk.jsonl` and `pin.json`. The silver writer
(plan row 6, `edgar-warehouse silver`) lands them: the three tables' specs are
registered once, then `silver land` reads each file. RDM does not write to the
silver database itself, so publishing never depends on it (ticket 06, 2026-10-08).

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
  in plan row 2: `place` is the label; its ISO 3166 codes become `exact`
  crosswalk rows to `iso-3166` (`outside`); its `type` (US, CANADIAN, FOREIGN,
  UNKNOWN) becomes a `broad` crosswalk row to a new 4-code set
  `sec-place-types` (operator, 2026-10-07), so "FOREIGN" never becomes a place
  code itself.
