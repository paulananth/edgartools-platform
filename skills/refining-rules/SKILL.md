---
name: refining-rules
description: Improve an existing feed or domain's mapping, data quality or matching rules in MDM. Measure changes on pinned captures, regenerate Mapping Documents, test and obtain operator approval of the exact version. Use data-onboarding for a new feed or domain.
---

# Refining Rules

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

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
| Switch on (activate) a version the operator has not told you to switch on | Ask, wait, record their exact words ([APPROVE.md](../data-onboarding/APPROVE.md)) |
| Approve with no test run | Run **test** first. A failing run may be overruled, a missing one never. |
| Ask the operator to approve a digest, hash or version number they cannot read | Say in plain words what the version does, what it changes and on what evidence, under its descriptive name; the digest goes beside it, never instead |
| Name a Rules version by a number alone | A label that says what it changes (the **test** step's version label, `<source or kind>-<YYYY-MM-DD>.<short change name>`) |
| Write a value from the data (a name, an identifier, a record) into a public repository | Counts, and invented examples; real values stay on the machine |
| Switch on a matching rule with no measured proof | A rule on an issued identifier is deterministic; any other rule needs a proof at its kind's bar |
| Request anything from a provider the operator has ruled out (data-onboarding, Examples) | Use the captured files and this repo |
| Read, print or paste a secret | Use the environment variables named in data-onboarding. If one is missing, ask. |
| Change what identifies a record inside one source code | A new source code (`….v2`) |
| Rewrite a batch MDM already took | A new version applies to new batches only |
| Ask several questions at once | Ask one, in plain words, with your recommendation |
| Put a master data field in silver, alone or as a copy | Every master data field is on its master in MDM, and only there (operator, 2026-10-28: "silver must not have duplicate fields, it contredits the data governance principle one system of record"): a change that finds one in silver moves it to the kind's fields and the Dataset Contract, then drops it from silver |

When two written decisions disagree, the later operator decision wins. Cite
both in the log.

## Shared with Data Onboarding

- **The contract language:** [REFERENCE.md](../data-onboarding/REFERENCE.md).
- **Approval and switch-on:** [APPROVE.md](../data-onboarding/APPROVE.md).
- **What MDM and RDM hold now:** `edgar-warehouse context <kind|relationship|code set>
  <key|--search words>` ([REFERENCE.md](../data-onboarding/REFERENCE.md), "Reading MDM's
  context"). Look up the records, links or codes a change moves, before and after.
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
- **Which target a field belongs to.** Review a live contract's MDM fields
  against data-onboarding's map rules ("Fields"): a date that usually changes
  stays out of MDM unless it adds meaning to the entity or switches it on or
  off; evidence about a transaction or a link goes on the silver row; another
  kind's identifier stays out; a code's label belongs in RDM (operator,
  2026-10-22: "Fix 1, 2 date that changes usually should not be in MDM unless
  it adds meaning to the entity or turn on or off"). Moving a field the
  engine or a stored table reads (a column, a matching check) is engine work:
  name each reader before you change the contract.

## Modes

Every change runs: the change mode → **test** → **approve** →
**switch-on**.

**A new delivery comes first.** When a live feed's new delivery arrived, run
[data-profiling](../data-profiling/SKILL.md)'s **compare** against the feed's
approved findings before changing anything. Each drift item names the skill
that handles it; the ones for refining-rules are the proposed changes, taken
one at a time with the modes below. Keep the approved findings'
`fingerprints.json` beside them: from it, compare also reports, per part,
whether the feed sends every record or changes only, how many keys persisted,
and the time between deliveries (`deliveries` in `drift.yaml`); a change of
delivery kind is a proposed change too (a full-file feed turned into changes
only changes how records are retired). A feed with no approved findings yet:
profile it with data-profiling first, and log it. After any change to a rules file, regenerate its Mapping
Document (`rules mapdoc write --only <source or kind>`) and commit it with
the change. `rules mapdoc check` and CI fail otherwise.
Adding or removing a field changes two workbooks: the source's
`MAPPING.xlsx` and its kind's (`rules/merge/kinds/<kind>.xlsx`, "Who wins each
field"). Regenerate both (`--only <source>`, then `--only <kind>`).

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

   Before a source order changes, measure it: data-profiling's
   `rank_sources.py` ("Rank several sources") gives each field's coverage,
   one-value rate and pairwise agreement per source, and an order. Put its
   numbers beside the change, and count the master records whose value moves.

   If you cannot make a change, say why in plain words and leave the rules
   as they are.
3. Regenerate: `rules mapdoc write --only <source or kind>`. The generated
   rows replace the steward's, so the steward confirms they say what was
   meant. Then `rules mapdoc check` must pass.
4. Continue with **test**. The steward who made the change approves it.

### change-quality: add or change a data quality check or fix

For when the operator asks about a live feed's data quality, a run's quality
counts look wrong, or **compare** lists drift handled by data-quality:
1. Read `rules/sources/<source>/quality.yaml`.
   - The counts of the last runs are in each run's report, if the operator
     has them.
   - With no run to read, measure them (step 2).
2. **Measure on one pinned capture.**
   - **Pin it:** the capture's `receipts.jsonl` (one line per file: key,
     sha256, bytes) is its manifest. Its sha256 is the `batch_hash`. Check
     each file's sha256 against its line. For a file's path, replace the
     key's leading `warehouse/bronze/` with `<capture>/bronze/`. The
     manifest lists exactly the files the measurement read (data-onboarding,
     **test**, "Input manifest"): add a joined file another source captured,
     and leave out a captured file the reading never opens.
   - **Build the records the checks read.** Run the candidate configured
     `read:` contract on the pinned files, then select the whole table rows or
     the explicit `mdm.prepare.record_column` objects. Preserve source types,
     unknown evidence and immutable input references. Use data-platform
     [READING.md](../data-platform/READING.md) for supported expressions.
     Where a live source's configured source extract does not yet cover its whole
     preparation (its ticket says what is open), the retained preparation
     stays an equivalence oracle until that part is qualified.
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
   - **Time:** measure a small pass first (a few hundred documents), then
     say how long the full pass will take before starting it. `rules mapdoc write` can take 10 minutes.
   - A zero count is only meaningful if the check can fire. Feed it one
     made-up record that should trip it, and label that input.
   - Report up to 10 examples of each check and fix.
3. **Decide and write with the data-quality skill.** Its
   [measure](../data-quality/SKILL.md) mode runs the candidate
   `quality.yaml` on the records built above and fires a planted record per
   check; its **decide** mode asks the operator about each `on_fail` and each
   fix, and its **write** mode gives `quality.yaml` a new `version` name. The
   source's contract changes with it, so this is a new source version, and
   every record re-read under it gets a new record id (data-quality,
   **write**). For
   a new defect a profile found, start at its **plan** mode with the
   delivery's approved findings.

### change-matching: add or tune a matching rule

For example: a cascade pass, a name rule, or records waiting for review.
1. Read `rules/merge/kinds/<kind>.yaml`, `rules/merge/policy.yaml` (what is
   switched on and why) and `rules/merge/pending-proofs.yaml`.
2. Describe the change in plain words: what it would join, and what it
   must never join (parent and subsidiary, a registered agent's address,
   the same name in two places).
3. **Measure it before it is switched on:**
   - A rule on an issued identifier is deterministic, and its proof is its
     Identifier Contract.
   - Any other rule needs a labelled sample of the links it adds, plus
     adversarial pairs, measured at its kind's bar (Examples). Record the
     proof in `pending-proofs.yaml`.
4. Show which records it moves. Use a proving run on a disposable
   PostgreSQL 16 (data-onboarding's test step): counts before and after,
   with examples.
5. A rule switched off, or a newer version, leaves the binds it already made
   standing. A correction batch revokes them and the active rules reconsider
   those records (`correction.correction_batch`: revoke, quarantine, lift),
   but it has no command yet (2026-10-23): log the records it would move, and
   ask before coding the command.
6. Update what a rule change moves, in the same branch: the whole policy's
   digest pinned as `policy_digest` in the mastering-records fixture under
   `tests/integration/fixtures/` (the failing test prints the new one), the
   kind's Mapping Document (`rules mapdoc write`), and the policy layers in
   `tests/mdm/policy_layers.py` when a kind they peel changes. The
   installed-bundle test (`tests/engine/test_data_skill_bundle_postgres.py`)
   builds from the last commit, so it agrees only after the change is
   committed.
7. Continue with **approve**, using "Switch one declared matching rule on"
   in APPROVE.md. A rule short of its bar stays off, and its records go to
   review.

A rule that asks whether two records state the same time compares them as
instants, never as text: the Stage stores a record's `effective_at` in UTC
(`+00:00`), while a census or a source keeps the provider's spelling (`Z`, an
offset). A source's record-keeping date that only marks a new version is that
record's effective time, not a field of the master (rebuild ticket 129).

### test: the cheapest proof, then record it

Prove the change at the level
[Choose the cheapest proof](../mdm-engineering/SKILL.md#choose-the-cheapest-proof)
names, and no further. Then `rules save` and record the proof, or carry the
last one forward (same table, its last row). Show what changes, record by
record.

### approve and switch-on

Follow [APPROVE.md](../data-onboarding/APPROVE.md). A new version applies
to new batches only. Running the feed is the Bookkeeping skill's **run**
mode.

When the operator asks for a limited test before a switch-on (ticket 138,
2026-10-26: "Do limited testing and switch on"): take a slice of the real
capture that holds the cases the rule changes (for a merge rule, the answers
sharing values with the slice), run it through the configured contracts and
the Merge Stage on a disposable store in every load order the feeds allow,
and a second pass. Write the counts only (records bound, masters, merges,
identifiers on two masters, open reviews, whether the orders give the same
masters, whether the second pass changed anything) to a file under
`.scratch/`; its sha256 is the new Identifier Contract's
`verification.corpus_sha256`. Say which case the slice did not hold.

## When a command is missing

Use the table in data-onboarding's SKILL.md, "When a command is missing".
Never invent a command.

## Examples (this repo's sources)

- A provider ruled out: `sec.gov`. A full pass over SEC submissions took
  about 3 minutes per 1,000 documents on a laptop.
- Open work on the live SEC Company and GLEIF pipelines: see data-onboarding's
  Examples, "Unfinished live pipelines" (one list, kept there).
- Issued identifiers: those with an Identifier Contract in a kind file (today `cik`; GLEIF states `lei`). Name-rule proofs:
  `.scratch/company-mastering/research/08-*` and `12-*`. A proving run:
  `.scratch/company-mastering/research/27_proving_run.py`.
