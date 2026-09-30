---
name: refining-rules
description: Improve a feed or domain that is ALREADY LIVE in Clean MDM and silver. Apply a steward's change to a Mapping Document, add or change a data quality check or fix, or add or tune a matching rule (e.g. the cascade passes, or records waiting for review). Then re-test, get the operator's (or steward's) approval and switch the change on. Use when the feed already has rules/sources/<source>/source.yaml, or the user says "mapping document", "data quality", "matching rule" or "merge rules" about something that exists. To bring in a new feed or domain, use data-onboarding.
---

# Refining Rules

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
- **The log:** `<your scratchpad>/refining-log.md`. Record each question and
  its answer, each missing command, and each guess.

## Two targets: MDM and silver

- **MDM target.** A change to a Dataset Contract, a quality check or a
  merge rule changes what MDM receives or joins. Show the records it moves.
- **Silver target.** A change to the `bookkeeping` section (the steps that
  land silver) belongs to the Bookkeeping skill. A quality fix applies to
  records before MDM; silver keeps the source's values.

## Modes

Every change runs: the change mode → **test** → **approve** →
**switch-on**. After any change to a rules file, regenerate its Mapping
Document (`rules mapdoc write --only <source or kind>`) and commit it with
the change. `rules mapdoc check` and CI fail otherwise.

### change-mapping: a steward changed a Mapping Document

A steward changes a workbook's cells (not only Notes) and commits it in a
PR.

1. List the changes:
   ```bash
   uv run --extra mdm edgar-warehouse rules mapdoc diff --only <source or kind>
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
1. Read `rules/sources/<source>/quality.yaml` and the counts of its last
   runs.
2. Run the dry run (data-onboarding **test**) on a pinned sample: the files
   of one capture, named by their sha256. Report the counts per check and
   fix, with up to 10 examples each.
3. Pick the check or fix from REFERENCE.md, "Data quality", using the same
   table as data-onboarding **quality**. Ask the operator about its
   `on_fail`, with its count and two or three examples.
4. Give `quality.yaml` a new `version` name. The source's contract changes
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
