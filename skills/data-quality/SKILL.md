---
name: data-quality
description: Turn the defects found while profiling a data set into data quality checks and fixes the engine runs on every load, measure them on the records, mark each invalid hierarchy row with an evidence-backed fix or "needs steward", and write the feed's quality.yaml after the operator decides each check. Use from data-onboarding's quality step (a new feed) and refining-rules' change-quality step (a live feed), or when the operator asks about a feed's data quality.
---

# Data Quality

> Part of the **data-platform** skill set. data-onboarding and refining-rules
> call it; it writes only `rules/sources/<source>/quality.yaml`.

It answers: **which defects does this part have, which check or fix carries
each, and what does each one do on the records?** Profiling finds the defects
(the `quality` items in `findings.yaml`, and `invalid_rows.jsonl` beside it).
This skill turns them into the engine's checks and fixes, measures them, and
writes them once the operator decides.

**Use the other skill when:**
- there are no approved findings yet: use **data-profiling** first;
- you are changing a live feed's mapping or matching: use **refining-rules**.

## Hard stops

| Never | Instead |
|---|---|
| Decide a check's `on_fail`, or keep a fix, for the operator | Ask one question per check or fix, with its count and two or three examples, and record their exact words |
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
Dataset Contract: the field each column fills.

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
| `check_digit` with a mod 97-10 family on 20 characters | `lei_check_digit@1` | withhold |
| any other `check_digit`, `link_not_found`, `hierarchy_invalid`, `no_natural_key` | none: new code | — |

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

It prints each check's count, compares it with profiling's, and fires a
planted record per check (exit 1 if a count differs or a planted record does
not fire). Read the counts carefully:
- An `exception` sets its record aside, so later checks do not see that
  record, as in a run.
- A count over records from the contract can be smaller than profiling's
  over the raw rows: the classification rule rejects some records first.
  Report both.
- A fix counts every record it touched, even when a later fix puts the value
  back. Report the net change too: records whose final value differs.
- Up to 10 examples per check and fix.

### decide: one question per check or fix

Pick each `on_fail` with the operator, with its count and examples:

| Problem | Check or fix |
|---|---|
| A code the source writes wrongly, or writes for "none" | A fix that blanks it (`blank_values@1`) |
| A value that must not match, but stays on the record (a placeholder, an agent's address) | A check with `on_fail: withhold` |
| A critical data element missing | A check with `on_fail: exception`. The record never merges and never stops the run; it waits as an open exception until fixed or ignored. Keep these few. |
| Anything worth watching | A check with `on_fail: flag` (only counted) |

- Every check reads the record after the mapping, never the raw file.
- What a check tests exactly: `present@1` on an address part also fires when
  there is no address at all. Say so, with both counts.
- A check limited to some records (a conditional check) is new code: log it
  for a ticket.
- Judging an existing fix: remove it in memory only, measure again, and
  compare record by record; then say whether a check would still catch those
  values without it.
- What is "right" (a code, a place) comes from the repository's reference
  tables and the contract's comments. When they cannot settle it, say so.

### mark: invalid hierarchy rows

`invalid_rows.jsonl`, beside `findings.yaml`, holds one line per row that
breaks a hierarchy's rule: its record key, the value, the reason (parent not
found, names itself as its parent, on a cycle, several parents, parent
differs), and a fix with its evidence, or `needs_steward: true`.
- A fix is proposed only with evidence: the one key equal to the value once
  case, spaces and leading zeros are folded; or the parent most rows with the
  same code have. Show the steward each fix with its evidence; they approve
  or reject it.
- Rows with no evidence go to the steward as they are.
- The rows stay marked, never dropped. The engine has no hierarchy check yet:
  the check is new code, listed in the plan.

### write: the feed's quality.yaml

- `rules/sources/<source>/quality.yaml`: `version`, then `quality`, one
  entry per source code; the format is in data-onboarding
  [REFERENCE.md](../data-onboarding/REFERENCE.md), "Data quality".
- A change is a new `version` name, so it is a new source version.
- List each `exception` check's reason `quality_<id>` in the contract's
  `nonblocking_deferred_reasons`, or registration refuses the contract.
- `files.write_source(body, folder)` writes `quality.yaml` without its
  comments. For a small change to a live file, edit it as text, keeping the
  comments.
- `files.source('<source>')` must load with `quality` inside each contract.

**Output:** `quality.yaml`, `QUALITY.md` with the operator's decisions, and
the measured counts, in the log.

## Examples

- A legal-entity register's identifier column with a mod 97-10 check digit
  on 20 characters becomes `lei_check_digit@1` with `on_fail: withhold`.
- A filer register writes `DC` as a state of incorporation and `000000000`
  for a missing tax number: the first is blanked (`blank_values@1`), the
  second is a placeholder (`placeholder@1`, withhold).
- A sales sample's customer state column, where three of 41 rows for one
  area code name another state: each row is marked with the fix "the state
  38 of 41 rows have", for the steward.
