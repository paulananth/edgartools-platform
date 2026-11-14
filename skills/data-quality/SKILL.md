---
name: data-quality
description: Analyze data quality defects, including tracing a mastered entity through every downstream field, and turn approved findings into checks the engine runs on every load. Use when profiling a feed, changing live quality rules, or auditing existing entity data across connected stores.
---

# Data Quality

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

> Part of the **data-platform** skill set. data-onboarding and refining-rules
> call it; remediation writes only `rules/sources/<source>/quality.yaml`.

It answers: **which rules does this part need, which defects does it have,
which check or fix carries each, and what does each one do on the records?**
Profiling proposes every rule the part needs, each with the rows that fail it
(the `quality` items in `findings.yaml`; `rows` above 0 is a defect, 0 a rule
the clean data passes, which still runs on every load), and marks invalid
hierarchy rows (`invalid_rows.jsonl` beside it). The Data Catalog shows the
same rules beside each silver field (data-profiling `catalog`).
This skill turns them into the engine's checks and fixes, measures them, and
writes them once the operator decides. For an existing-data audit, it can also
produce a read-only analysis of a mastered entity and its downstream fields;
that analysis does not itself change quality configuration.

**A part that goes to silver** (transaction or event data, published
reference data) has no `quality.yaml`: those checks read MDM records only.
Fix what the reading can fix there (a date written with a time-zone offset
read as a calendar date, the spellings of one flag looked up to a boolean,
codes read against their full list from its authority, not one sample's) and
type it in its silver spec. Every other rule goes in the spec's `checks`
(`docs/specs/profiling/findings.md`, section 6): `identifier` (a declared
identifier type), `in_set`, `one_value` (one value per group, which carries
a reference hierarchy's rule), `not_after` (a start is not after its end) and
`reason_if_empty` (a value is empty exactly when its reason column is filled). A row failing a `flag` check lands with the
check's id in its `quality` column (operator: "Flag, land the
row"); `exception` keeps it out. Measure each check on the delivery first,
with the writer's own code (`edgar_warehouse.silver_writer.checks.run`), and
write each count in the check's comment; a check that flags rows the source
gives on purpose is no check. A rule none of the three carries is new code:
log it for a ticket.

**Use the other skill when:**
- there are no approved findings yet: use **data-profiling** first;
- you are changing a live feed's mapping or matching: use **refining-rules**.

## Trace a mastered entity through downstream data

Use this mode when the operator asks to follow a known entity from its master
record through all downstream fields, then repeat that review for a population.
Treat the previously reviewed entity as a method example, not as proof that
other entities have the same values or defects.

1. Start from the authoritative master key and a fixed, read-only snapshot.
   Follow only declared identifiers, foreign keys, contracts, and configured
   transformations; record the exact key used at each join.
2. Discover every in-scope downstream table from the live schema, contracts,
   rules, and reader/writer paths. Include every field carried for the entity,
   including nested fields, derived values, typed relationship edges, and
   identifier cross-references. Verify relationship direction and both
   endpoint kinds, and trace cross-references through their configured
   identifier path. Follow the operator's layer boundary; do not add analytics
   or other destinations that were not requested.
3. For every entity and downstream field, measure whether it is present,
   absent by design, unresolved, duplicated, stale, malformed, or in conflict.
   Compare values only with the configured source, mapping, survivorship, or
   derivation rule that governs that field. A difference is not a defect until
   the governing meaning is established.
4. Cover the full named population. A single entity can prove the trace path,
   but cannot establish population-wide coverage or quality. Report a count and
   denominator for each result, including zero counts; identify any record or
   field the available stores could not trace.
5. Group issue candidates by one evidenced failure pattern. For each, state
   the affected layer, table and field; population count and denominator; the
   expected and observed behavior; impact; the evidence snapshot and rule
   version; and a root-cause hypothesis clearly marked as unconfirmed. Keep
   examples masked and separate measured facts from interpretation.
6. Deliver issue-ready analysis only. Do not alter stores, mappings, rules,
   quality configuration, catalogs, or create tickets as part of this audit.
   Convert an agreed finding into a ticket only when the operator asks.

## Hard stops

| Never | Instead |
|---|---|
| Decide a check's `on_fail`, or keep a fix, outside the table | The table in **decide** settles it under the standing rule approval, with its count; ask one question, with two or three examples, only where the table does not |
| Write a check or fix the engine does not have | List it as new code, for a ticket (the plan does this for you) |
| Trust a zero count | A planted record must make each check fire first |
| Drop or change an invalid row | Mark it; a fix needs evidence and a steward's approval, otherwise it "needs steward" |
| Print a raw personal value | Examples and marked rows of a personal column are masked to their shape |
| Write `quality` inside `source.yaml` | `quality.yaml` holds it; the loader refuses it in `source.yaml` |

### Approved provisional dates

When the operator permits a file date while a true business start is unknown,
keep the true start unknown. Name the exact source date field, preserve its
provenance and use an **observed** start in the existing temporal model. Check
required endpoint registrations cover that interval. Never substitute today's
date for a missing or invalid source date.

Flag the missing authoritative start with a nonblocking check; the approved
provisional link remains valid. This flags the missing business fact, not an
incorrectly supplied file date. Measure its coverage and failures on the
retained scope and publish the genuine results and the provisional policy in
the catalog. A successful load does not clear this defect. When authoritative
evidence arrives, replace the observed fallback under the correction workflow,
update affected registration periods and retain the earlier evidence.

## Setup

The helper runs where the platform is installed, because it uses the
engine's own checks:

```
uv run python <this skill's folder>/scripts/quality_plan.py --help
```

## Existing master projections

Use this procedure for source-backed winner fields in an existing MDM
projection.

When an audit examines fields already selected into master records, first pin
the projection generation and compare each stored field-authority fingerprint
and kind version with the policy configured for that generation. For a
full-population comparison, use one repeatable-read snapshot and bounded
primary-key pages. Keep raw rows traversed separate from canonical, non-alias
masters, and report the accepted field denominator and mismatch count by kind
and mismatch class. Do not combine denominators or policy shares from different
snapshots.

For each accepted, source-backed field projection, follow its winner to the
retained assertion and compare source code, record key, effective time, claim
presence, operation, winner value, projected value, and clear state. Aggregate
mismatches without emitting record keys or field values. Zero mismatches prove
that the selected projection agrees with its retained claim; they do not prove
that the business value or selected winner is correct. If the stored authority
differs from the policy being assessed, report stale projection provenance and
keep those fields out of current-policy defect counts until source identity,
effective time, and the intended generation are reconciled. A source name or
field-presence count alone is not a quality failure.

## Cross-store pointers

Before assessing a nullable downstream pointer, read its declared source key,
source binding, target kind, null policy, and time basis. Pin the Silver landing
and MDM generations. Classify the key as absent, unmatched, uniquely resolved,
ambiguous or held, or uniquely resolved without a source binding. An identifier
match alone does not prove the configured source route exists. Count a pointer
as a defect only when the pinned contract requires it, one authoritative target
and source binding exist for that generation and time, and the verified landing
is null or points elsewhere. Keep expected no-key, unmapped, ambiguous, deferred,
and review-held cases separate; never turn them into a blanket nonnull check.
Trace any declared source time through the reading and preparation stages to the
stored assertion or relationship. A contract description does not prove that
the loader materialized the time. Keep a publication's effective time separate
from a relationship's own start date, and preserve date-only, timezone, and
observed-file-date semantics without inventing a conversion.
If the available quality primitive cannot express this comparison, document
the required cross-store capability and prove it with a planted invalid pointer
before proposing activation.

## Modes, in order

**plan → measure → decide → mark → write.** For a live feed, start at
**measure** with the feed's current `quality.yaml`.

### plan: findings into checks

You need the part's approved `findings.yaml` and a map from each source
column the items name to the record path a check reads (`fields.<name>`,
`fields.address.<part>` or `matching.<name>`). The map comes from the part's
Dataset Contract: the field each column fills, as its reading's `fields` and
`matching` columns state it.

```
uv run python <this skill's folder>/scripts/quality_plan.py draft \
  --findings <folder>/findings.yaml --part <part> --map <map.yaml> \
  --version <name>-quality-v1 --source-code <code> --out <folder>
```

It writes `quality.yaml` (checked by the engine's own `check_quality`),
`expected.yaml` (profiling's count per check) and `QUALITY.md`:

| Profiling item | Engine check | Proposed `on_fail` |
|---|---|---|
| `missing`: an empty record key column | `present@1` | exception |
| `placeholder`: a stand-in for no value | `placeholder@1` | withhold |
| `shape_outlier`: a value off the column's one shape | `pattern@1` | flag |
| `code_list`: a small code list | `in_set@1` (a code not seen is flagged) | flag |
| any item proposed as `blank`, with the values to blank | `blank_values@1` (a fix) | — |
| `check_digit` with a mod 97-10 family on 20 characters | `lei_check_digit@1` | withhold |
| `check_digit` whose family and length a declared identifier type has (`rules/identifiers/<name>.yaml`) | none: the Dataset Contract that formats the column with the type sets the record aside as `invalid_<name>_checksum`; list that reason in `nonblocking_deferred_reasons` | — |
| any other `check_digit`, `link_not_found`, `hierarchy_invalid`, `no_natural_key` | none: new code, with what its check would test (for `hierarchy_invalid`, see below) | — |

An item whose column has no field in the map is listed as "no field mapped":
map the column, or leave the item out and say why in the log.

### measure: counts on the records

Build the records the checks read, one JSON object per line with its
`fields` and `matching`:
- a new feed: as in data-onboarding **test**;
- a live feed: as in refining-rules **change-quality**, "Build the records
  the checks read", on one pinned capture.

```
uv run python <this skill's folder>/scripts/quality_plan.py measure \
  --quality <folder>/quality.yaml --source-code <code> --records <records.jsonl> \
  [--expected <folder>/expected.yaml]
```

It checks the file as the rules loader and registration do (and names the
`exception` reasons the contract must list as non-blocking), prints how many
records each fix changed and each check fired on, compares them with
profiling's, and fires a planted record per check (exit 1 if a count differs
or a planted record does not fire). Read the counts carefully:
- Each check is counted on its own, as profiling counts it. In a run, an
  `exception` sets its record aside, so later checks do not see that record:
  a run's counts can be smaller.
- A count over records from the contract can be smaller than profiling's
  over the raw rows: the classification rule rejects some records first.
  Report both.
- A fix counts every record it touched, even when a later fix puts the value
  back. Report the net change too: records whose final value differs.
- Profiling's examples (up to three per item, masked for a personal
  column) are in the findings; show two or three when you ask.

### decide: the table decides; ask only what it cannot

Pick each `on_fail` from the table below, with its count and examples.
Where the table decides, record it under the operator's standing rule
approval with those counts (operator: "Approved the rules
always"); ask one question only where it does not, or where a count disagrees
with profiling's:

| Problem | Check or fix |
|---|---|
| A code the source writes wrongly, or writes for "none" | A fix that blanks it (`blank_values@1`) |
| A value that must not match, but stays on the record (a placeholder, an agent's address) | A check with `on_fail: withhold` |
| A critical data element missing | A check with `on_fail: exception`. The record never merges and never stops the run; it waits as an open exception until fixed or ignored. Keep these few. |
| Anything worth watching | A check with `on_fail: flag` (only counted) |

- **A check:** ask about its `on_fail`. **A fix:** there is no `on_fail`;
  ask whether to keep it, change it or remove it.
- Every check reads the record after the mapping, never the raw file.
- What a check tests exactly: `present@1` on an address part also fires when
  there is no address at all. Say so, with both counts.
- A check limited to some records (a conditional check) is new code: log it
  for a ticket.
- Judging an existing fix: remove it in memory only, measure again, and
  compare record by record; then say whether a check would still catch those
  values without it.
- What is "right" (a code, a place) comes from the reference tables under
  `rules/reference/` and the contract's comments. When they cannot settle it, say so.

### mark: invalid hierarchy rows

`invalid_rows.jsonl`, beside `findings.yaml`, holds one line per row that
breaks a hierarchy's rule: its record key, the value, the reason (parent not
found, names itself as its parent, on a cycle, several parents, parent
differs), and a fix with its evidence, or `needs_steward: true`.
- A fix is proposed only with evidence: the one key equal to the value once
  case, spaces and leading zeros are folded; or the parent most rows with the
  same code have. Show the steward each fix with its evidence; they approve
  or reject it.
- A value meant to be a code of a published code set: look it up, or search
  the code set's labels and synonyms, with
  `edgar-warehouse context <code set> <code>` or
  `edgar-warehouse context <code set> --search "<words>"`. A unique match is
  evidence for a fix; several matches, or none, go to the steward.
- Rows with no evidence go to the steward as they are.
- The rows stay marked, never dropped. The plan does not write a hierarchy
  check itself. Once the hierarchy's code set is published and pinned in RDM
  and the record carries both the code and its parent, write `in_hierarchy@1`
  by hand (`field`: the parent's path; with `present@1` on the parent when a
  missing parent matters): it checks each record's parent code on every load,
  a quality version for the operator's approval, as any check.

### write: the feed's quality.yaml

- `rules/sources/<source>/quality.yaml`: `version`, then `quality`, one
  entry per source code; the format is in data-onboarding
  [REFERENCE.md](../data-onboarding/REFERENCE.md), "Data quality".
- A change is a new `version` name, so it is a new source version.
- Each record names the quality version it was read under, so a new
  version gives every re-read record a new record id. Say so when asking
  for approval. A test that pins record ids keeps comparing under the old
  version, and shows that the version name is the only change.
- List each `exception` check's reason `quality_<id>` in the contract's
  `nonblocking_deferred_reasons`, or registration refuses the contract.
- `files.write_source(body, folder)` writes `quality.yaml` without its
  comments. For a small change to a live file, edit it as text, keeping the
  comments.
- `files.source('<source>')` must load with `quality` inside each contract.
- **No checks, no file.** When the plan drafts no check and no fix (each
  item set aside by an identifier type, or a disagreement between source rows
  that one record cannot show), write no `quality.yaml`: an empty one adds a
  quality version and changes every record id for nothing. Say why in the
  log, and give a row-level disagreement its own ticket.

**Output:** `quality.yaml`, `QUALITY.md` with the operator's decisions, and
the measured counts, in the log.

### read: the run's checks

Every MDM run keeps `checks` in its report, per source. They never block:
- `records` and `set_aside`: a set-aside share that jumps from the last run
  is a delivery or mapping problem; look at its reasons first.
- `empty_rate` per field, over the records that merge (a field left out,
  unknown or blank counts as empty): a field that used to be filled and is
  now empty points at a renamed or moved source field.
- `newest` and `newest_age_days` on the run's `as_of`: `None` means the
  records state no time (map `effective_at`, data-onboarding), not that the
  data is fresh.
A change worth a check becomes a check here (**plan**), not a note.

## Check kinds: what outside standards add (DataKitchen TestGen)

Research note: `docs/research/datakitchen-testgen-test-types-2026-11-02.md` (the
open-source TestGen repository, 89 test types, each one declarative file).
Take its design, not its tool:

- **A check is a rule, never code.** Each check is a row in the rules file
  (`id`, `check` kind, the columns, the kind's parameters, `on_fail`, `why`).
  TestGen does the same: a type is a file naming its description, parameters,
  default severity, scope (column, table, referential) and a threshold that
  counts the bad rows tolerated. The engine holds only generic kinds; a column
  or a table name in engine code is a defect. A rule no kind carries is a new
  kind (one generic function plus its tests), then declared in the rules.
- **Read the column's type first.** A kind has a column type it accepts
  (`in_set` reads a text column with text values, or a `BIGINT` column with
  whole-number values, as every integer is `BIGINT`; the catalog refuses anything
  else). A numeric closed list on a decimal column needs its own kind, not a text copy of the column.
- **The table's key already checks the key.** A silver table's `PRIMARY KEY`
  refuses a repeated or empty key column, so TestGen's unique-key and required
  types need no check kind for the key; add a kind only for a rule the table
  cannot state.
- **Values come from rules, not from a sample.** TestGen's baseline types fill
  their lists from a profile of the data; here a closed list comes from the
  rules file or its code list in the reference store, and a count measured on
  the delivery goes in the comment (see above), never into the list.
- **Order by what a defect costs.** After the kinds this engine has
  (`identifier`, `in_set`, `one_value`, `not_after`, `reason_if_empty`), the kinds that find most are: a unique
  key (an append-only table shows a replay as a repeated key; a snapshot shows
  a rebuild that did not replace), a required column (a null key defeats the
  uniqueness check), a bound (a date in the future; a date order is `not_after`), a row condition over columns, a pattern, a second-table match, and
  volume or freshness per delivery. Statistical drift types need a baseline run
  this platform does not keep; leave them out of a first set.
- **`one_value` has no TestGen twin.** "Within a group one value, flag the
  minority" is this engine's own kind; it carries rules such as the rows of one
  document agreeing on what the document is. Keep it for group consistency.
- **Name the dimension in the `why`** (completeness, validity, consistency,
  uniqueness, timeliness): the business catalog groups cases by it.
- **Start with the checks that run today**, measure each on the delivery, and
  list the others as the work for a new kind.

## Examples

- A legal-entity register's identifier column with a mod 97-10 check digit
  on 20 characters becomes `lei_check_digit@1` with `on_fail: withhold`.
- A filer register writes `DC` as a state of incorporation and `000000000`
  for a missing tax number: the first is blanked (`blank_values@1`), the
  second is a placeholder (`placeholder@1`, withhold).
- A sales sample's customer state column, where three of 41 rows for one
  area code name another state: each row is marked with the fix "the state
  38 of 41 rows have", for the steward.


## Publish quality meaning to the business catalog

Use [Business catalog](../data-onboarding/CATALOG.md) for catalog publication.
Publish configured checks as named native test-case definitions, retaining their
inputs, failure actions and configuration references. Keep fixes as corrections
and profiling proposals as proposals. Do not translate engine checks into guessed
SQL or manufacture pass/fail results. Result publication requires genuine matched
execution evidence. A quality description in a column is not native test-case
coverage; missing publisher support is an implementation gap.

### MDM execution evidence

MDM checks remain in each source's registered quality contract. All source
adapters use the shared quality evaluator and emit the same versioned evidence
shape; do not add source-specific result adapters or entity branches. Counts
identify checks by the configured check id and check kind, and distinguish
`flag`, `withhold`, and `exception`. An exception ends evaluation for that
record at the failed check; later checks are unknown for that record. Missing
or incomplete evidence is never a pass or fail.

MDM evidence is opt-in and stays disabled until the recovery qualification and
operator enablement in [Bookkeeping recovery](../bookkeeping/RECOVERY.md) are
complete. Bookkeeping admits immutable unit receipts. OpenMetadata is the
single user-facing results surface; it receives only counts from verified
work, and incomplete evidence is recorded as `Aborted` with explicit
incomplete/unknown detail and exact readback.
