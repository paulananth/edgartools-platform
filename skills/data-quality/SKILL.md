---
name: data-quality
description: Turn the defects found while profiling a data set into data quality checks and fixes the engine runs on every load, measure them on the records, mark each invalid hierarchy row with an evidence-backed fix or "needs steward", and write the feed's quality.yaml after the operator decides each check. Use from data-onboarding's quality step (a new feed) and refining-rules' change-quality step (a live feed), or when the operator asks about a feed's data quality.
---

# Data Quality

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

> Part of the **data-platform** skill set. data-onboarding and refining-rules
> call it; it writes only `rules/sources/<source>/quality.yaml`.

It answers: **which rules does this part need, which defects does it have,
which check or fix carries each, and what does each one do on the records?**
Profiling proposes every rule the part needs, each with the rows that fail it
(the `quality` items in `findings.yaml`; `rows` above 0 is a defect, 0 a rule
the clean data passes, which still runs on every load), and marks invalid
hierarchy rows (`invalid_rows.jsonl` beside it). The Data Catalog shows the
same rules beside each silver field (data-profiling `catalog`).
This skill turns them into the engine's checks and fixes, measures them, and
writes them once the operator decides.

**A part that goes to silver** (transaction or event data, published
reference data) has no `quality.yaml`: those checks read MDM records only.
Fix what the reading can fix there (a date written with a time-zone offset
read as a calendar date, the spellings of one flag looked up to a boolean,
codes read against their full list from its authority, not one sample's) and
type it in its silver spec. Every other rule goes in the spec's `checks`
(`docs/specs/profiling/findings.md`, section 6): `identifier` (a declared
identifier type), `in_set` and `one_value` (one value per group, which carries
a reference hierarchy's rule). A row failing a `flag` check lands with the
check's id in its `quality` column (operator, 2026-10-17: "Flag, land the
row"); `exception` keeps it out. Measure each check on the delivery first,
with the writer's own code (`edgar_warehouse.silver_writer.checks.run`), and
write each count in the check's comment; a check that flags rows the source
gives on purpose is no check. A rule none of the three carries is new code:
log it for a ticket.

**Use the other skill when:**
- there are no approved findings yet: use **data-profiling** first;
- you are changing a live feed's mapping or matching: use **refining-rules**.

## Hard stops

| Never | Instead |
|---|---|
| Decide a check's `on_fail`, or keep a fix, outside the table | The table in **decide** settles it under the standing rule approval, with its count; ask one question, with two or three examples, only where the table does not |
| Write a check or fix the engine does not have | List it as new code, for a ticket (the plan does this for you) |
| Trust a zero count | A planted record must make each check fire first |
| Drop or change an invalid row | Mark it; a fix needs evidence and a steward's approval, otherwise it "needs steward" |
| Print a raw personal value | Examples and marked rows of a personal column are masked to their shape |
| Write `quality` inside `source.yaml` | `quality.yaml` holds it; the loader refuses it in `source.yaml` |

## Setup

The helper runs where the platform is installed, because it uses the
engine's own checks:

```
uv run python <this skill's folder>/scripts/quality_plan.py --help
```

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
approval with those counts (operator, 2026-10-15: "Approved the rules
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

## Examples

- A legal-entity register's identifier column with a mod 97-10 check digit
  on 20 characters becomes `lei_check_digit@1` with `on_fail: withhold`.
- A filer register writes `DC` as a state of incorporation and `000000000`
  for a missing tax number: the first is blanked (`blank_values@1`), the
  second is a placeholder (`placeholder@1`, withhold).
- A sales sample's customer state column, where three of 41 rows for one
  area code name another state: each row is marked with the fix "the state
  38 of 41 rows have", for the steward.
