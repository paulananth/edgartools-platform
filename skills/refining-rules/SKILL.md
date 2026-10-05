---
name: refining-rules
description: Improve an existing feed or domain's mapping, data quality or matching rules in Clean MDM. Measure changes on pinned captures, regenerate Mapping Documents, test and obtain operator approval of the exact version. Use data-onboarding for a new feed or domain.
---

# Refining Rules

> Part of the **data-platform** skill, installed as one package with its
> commands. Start there for setup (install, stores, `edgar-warehouse doctor`)
> and for the whole flow; this skill holds one step's detail.

Changes something **already live**: a feed with a rules file, or a domain
with merge rules.

**Use the other skill when:**
- the feed or domain has no rules file yet: use **data-onboarding**;
- you are running a feed, or recovering a run: use **bookkeeping**;
- you are recording or recovering journal evidence: use **change-journal**.

## Hard stops

| Never | Instead |
|---|---|
| Approve for the operator or a steward, or record words they did not say | Ask, wait, record their exact words ([APPROVE.md](../data-onboarding/APPROVE.md)) |
| Approve with no test run | Run **test** first. A failing run may be overruled, a missing one never. |
| Switch on a matching rule with no measured proof | A rule on an issued identifier is deterministic; any other rule needs a proof at its kind's bar |
| Request anything from `sec.gov` | Use the captured files and this repo |
| Read, print or paste a secret | Use the environment variables named in data-onboarding. If one is missing, ask. |
| Change what identifies a record inside one source code | A new source code (`….v2`) |
| Rewrite a batch MDM already took | A new version applies to new batches only |
| Ask several questions at once | Ask one, in plain words, with your recommendation |

When two written decisions disagree, the later operator decision wins. Cite
both in the log.

## Shared with Data Onboarding

- **The contract language:** [REFERENCE.md](../data-onboarding/REFERENCE.md).
- **Approval and switch-on:** [APPROVE.md](../data-onboarding/APPROVE.md).
- **How to run commands, the environment variables, and the dry run**
  (`test` mode): see data-onboarding's SKILL.md, "How to run commands" and
  "test".
- **The log:** `.scratch/onboarding/<source>/refining-log.md` on your
  branch, never a temporary folder. In a sandbox or trial, keep the log and
  your draft rules together, as in data-onboarding's "Where you write"
  (a copy of `rules/`, passed as `root=` / `--root`). When you follow a data-onboarding step,
  log it here too. Record each question and its answer, each missing
  command, and each guess.

## Two targets: MDM and silver

- **MDM target.** A change to a Dataset Contract, a quality check or a
  merge rule changes what MDM receives or joins. Show the records it moves.
- **Silver target.** A change to the `bookkeeping` section (the steps that
  land silver) belongs to the Bookkeeping skill. A quality fix applies to
  records before MDM; silver keeps the source's values.

## Modes

Every change runs: the change mode → **test** → **approve** →
**switch-on**.

**A new delivery comes first.** When a live feed's new delivery arrived, run
[data-profiling](../data-profiling/SKILL.md)'s **compare** against the feed's
approved findings before changing anything. Each drift item names the skill
that handles it; the ones for refining-rules are the proposed changes, taken
one at a time with the modes below. A feed with no approved findings yet:
profile it with data-profiling first, and log it. After any change to a rules file, regenerate its Mapping
Document (`rules mapdoc write --only <source or kind>`) and commit it with
the change. `rules mapdoc check` and CI fail otherwise.

### change-mapping: a steward changed a Mapping Document

A steward changes a workbook's cells (not only Notes) and commits it in a
PR.

1. List the changes:
   ```bash
   edgar-warehouse rules mapdoc diff --only <source or kind>
   ```
   It prints each changed cell: the sheet, row and column, what the rules
   say, and what the workbook says. A spreadsheet does not show its changes
   in a PR, so paste this list into the PR.
2. Turn each change into the rules files:

   | Workbook change | Rules change |
   |---|---|
   | A row added to "Critical data elements" | A `present@1` check with `on_fail: exception` in `quality.yaml`, with its reason `quality_<id>` in `nonblocking_deferred_reasons` |
   | "Preferred sources" reordered | `defaults.sources` in the kind file |
   | One field's winner changed ("Who wins each field") | `fields.<name>.sources` in the kind file, in the new order. Every other field keeps the default. A source left out is ignored for that field; say so. |
   | A source added to a kind | Not the steward's decision: it needs the operator's ruling |
   | An identifier or record key changed | A new source code (`….v2`) |
   | A check or fix not in REFERENCE.md | New code: log it for a ticket |
   | A new MDM field or kind | The operator's ruling |

   If you cannot make a change, say why in plain words and leave the rules
   as they are.
3. Regenerate: `rules mapdoc write --only <source or kind>`. The generated
   rows replace the steward's, so the steward confirms they say what was
   meant. Then `rules mapdoc check` must pass.
4. Continue with **test**. The steward who made the change approves it.

### change-quality: add or change a data quality check or fix

For when the operator asks about a live feed's data quality, or a run's
quality counts look wrong:
1. Read `rules/sources/<source>/quality.yaml`.
   - The counts of the last runs are in each run's report, if the operator
     has them.
   - With no run to read, measure them (step 2).
2. **Measure on one pinned capture.**
   - **Pin it:** the capture's `receipts.jsonl` (one line per file: key,
     sha256, bytes) is its manifest. Its sha256 is the `batch_hash`. Check
     each file's sha256 against its line. For a file's path, replace the
     key's leading `warehouse/bronze/` with `<capture>/bronze/`.
   - **Build the records the checks read.** Run the candidate configured
     `read:` contract on the pinned files, then select the whole table rows or
     the explicit `mdm.prepare.record_column` objects. Preserve source types,
     unknown evidence and immutable input references. Use data-platform
     [READING.md](../data-platform/READING.md) for supported expressions.
     Company raw columns alone omit catalog/census joins and full address/
     pagination preparation; retained preparation remains an equivalence
     oracle until those operations are qualified. GLEIF likewise retains its
     archive/publication validation until bounded streaming is implemented.
     Label diagnostic runs on retained preparation as such; they do not prove
     a configured replacement. Test grammar support before proposing custom
     code, and use data-platform Mode 6 only for a demonstrated grammar gap.
   - **Count two ways, and report both:**
     - **All filers:** `adapters.mapped_values(row, contract)` returns each
       record's `quality` block.
     - **What MDM receives:** `adapters.normalize(...)`, as in
       data-onboarding **test**. It sets aside records the classification
       rule rejects before the quality checks run, so its counts are
       smaller. For a capture with one file per record, pass
       `publication={"artifact_sha256": <that file's sha256>, "member":
       <its receipt key>, "publication_key": "dry-run", "revision": 0}`.
       Collect each `UnsupportedRecord` as `{"reason": exc.args[0]}` and
       pass that list to `quality.counts(records, deferred)`.
   - **Read the counts carefully:**
     - A fix counts every record it touched, even when a later fix puts the
       value back. Report the net change too: records whose final value
       differs.
     - A standardising fix (the address one) touches most records. That is
       expected, not a defect.
   - **Time:** a full pass reads every file and takes about 3 minutes per
     1,000 SEC documents on a laptop. Try 200 first, then say how long the
     full pass will take. `rules mapdoc write` can take 10 minutes.
   - A zero count is only meaningful if the check can fire. Feed it one
     made-up record that should trip it, and label that input.
   - Report up to 10 examples of each check and fix.
3. **Decide with the operator.** Pick the check or fix from REFERENCE.md,
   "Data quality", using the same table as data-onboarding **quality**.
   - **A check:** ask about its `on_fail` (exception, withhold or flag),
     with its count and two or three examples.
   - **A fix:** there is no `on_fail`. Ask whether to keep it, change it or
     remove it, with its count and examples.
   - **What a check tests exactly:** `present@1` on
     `fields.address.postcode` also fires when there is no address at all.
     Say so, with both counts. A check limited to some records (e.g. US
     addresses only) is a conditional check, which is new code: log it for
     a ticket.
   - **Judging an existing fix:** remove it in memory only, rerun, and
     compare record by record. Then say whether any check would still catch
     those values without it.
   - **What is "right"** (e.g. a state code) comes from the repo:
     `rules/reference/sec-place-codes.yaml` and the contract's comments.
     When the files cannot settle it, say so.
4. **Write the change.** `files.write_source` rewrites `quality.yaml`
   without its comments. For a small change, edit the file as text instead,
   keeping the comments, then check that `files.source('<source>')` still
   loads and holds the new check. Give `quality.yaml` a new `version`
   name. The source's contract changes
   with it, so this is a new source version.

### change-matching: add or tune a matching rule

For example: a cascade pass, a name rule, or records waiting for review.
1. Read `rules/merge/kinds/<kind>.yaml`, `rules/merge/policy.yaml` (what is
   switched on and why) and `rules/merge/pending-proofs.yaml`.
2. Describe the change in plain words: what it would join, and what it
   must never join (parent and subsidiary, a registered agent's address,
   the same name in two places).
3. **Measure it before it is switched on:**
   - A rule on an issued identifier (`cik`, `lei`) is deterministic, and its
     proof is its Identifier Contract.
   - Any other rule needs a labelled sample of the links it adds, plus
     adversarial pairs, measured at its kind's bar. The examples are
     `.scratch/company-mastering/research/08-*` and `12-*`. Record the proof
     in `pending-proofs.yaml`.
4. Show which records it moves. Use a proving run on a disposable
   PostgreSQL 16 (`.scratch/company-mastering/research/27_proving_run.py`):
   counts before and after, with examples.
5. Continue with **approve**, using "Switch one declared matching rule on"
   in APPROVE.md. A rule short of its bar stays off, and its records go to
   review.

### test: re-run on real captured files and record it

As in data-onboarding **test**: dry run or proving run, then
`rules save` and `rules record-proof`. Show what changes, record by record,
from the dry run before and after.

### approve and switch-on

Follow [APPROVE.md](../data-onboarding/APPROVE.md). A new version applies
to new batches only. Running the feed is the Bookkeeping skill's **run**
mode.

## When a command is missing

Use the table in data-onboarding's SKILL.md, "When a command is missing".
Never invent a command.
