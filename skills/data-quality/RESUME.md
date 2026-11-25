# Resume Data Quality

Use the source's existing [Data Platform `## Resume` record](../data-platform/RESUME.md),
under `Phase` and `Next action`. Keep the checklist for each part there;
do not create another progress log. Use Data Onboarding for a new source
or Refining Rules for a live source as the owning skill on the shared record;
name Data Quality and its first unfinished step in `Next action` while it has work.

| Evidence in `Phase` | Reuse | Reopen or block |
|---|---|---|
| Approved findings; mapped fields; check definitions, version, and evaluator revision | Reuse the draft when the hashes and revisions match. | A changed finding, mapping or check definition reopens drafting and dependent evidence. A changed evaluator reopens the steps that used it. Missing artifacts or new unapproved findings block the affected work. |
| Selected capture manifest, mapped corpus, counts and planted-record results, by check | Reuse only if the complete check definition, evaluator, measured input and evidence hashes match. | A different selected delivery or mapped corpus invalidates dependent measurements; use approved evidence for the selected delivery before measuring again. Missing evidence or damage to the recorded capture blocks; a count mismatch or a check that cannot be made to fire leaves verification unfinished. |
| Failure actions, row dispositions, unresolved defects and approvals | Carry each decision with its supporting measurement and reason; keep unresolved defects visible. | An invalidated measurement reopens the disposition it supported, not unrelated decisions. A missing required approval or steward decision blocks the affected item. |
| Draft and handoff artifacts: `quality.yaml` or the Silver check proposal, `QUALITY.md`, and row dispositions | Hand over the same artifact hashes to the recorded owner. | Reopen a handoff whose evidence changed. Data Catalog owns the business meaning; a draft or a local measurement is not a catalog execution result. |

Record paths, hashes, counts and decisions, not data values or credentials.
Select the earliest invalidated action or first unchecked action; skip earlier
verified steps whose evidence still matches. Retain the old evidence marked stale.

## Add draft rules with TestGen

When TestGen is requested, use DataKitchen TestGen to define and measure draft
checks on authorized, pinned inputs in a local or otherwise approved test suite.
Do not connect it to a live source, enable schedules or export observations as
part of this step. TestGen detects defects; the platform's approved rule files
and owning phase govern enforcement, failure actions, and activation.

1. From approved findings and the Dataset Contract field map, choose a built-in
   TestGen type with the same measure, null and blank semantics as the
   intended rule. Record purpose, table/column, threshold and the authority for
   its parameters. For `LOV_Match`, use the declared allowed list, not sample
   frequencies; it excludes null and empty strings. `Required` counts nulls,
   not empty strings. Keep a distinct completeness test when needed.
2. Create a `version: 1` definition-import JSON document with `definitions`.
   Give each manual rule a stable `external_id` UUID and specify `test_type`,
   `table_name`, `column_name`, `threshold_value` and its type-specific parameters
   (for `LOV_Match`, `baseline_value`). Use trusted declared values, not SQL
   from findings. Keep native platform check kinds when TestGen has no equivalent.
3. Profile the mapped table in the test suite's table group if its catalog
   does not yet contain the table and columns. Use the
   [TestGen import API](https://docs.datakitchen.io/testgen/api/import-and-export-tests/)
   in `preview` mode with `on_match: skip`, `on_new: create`, and
   `on_absence: do_nothing`. Review every planned creation. Apply with
   `apply_strict` only to the approved test suite when every included rule is
   new and valid. If a rule already exists, read it back by `external_id` and
   compare its definition before carrying it forward; do not overwrite it on
   resume. Keep export to observability disabled.
4. Run only the intended suite on the pinned corpus and retain its rule
   readback, run ID, measured failure counts, and a planted case for each rule.
   In `Phase`, record the TestGen release, suite identity, draft hash, corpus
   hash, result evidence and a hash of the exported definitions sorted by
   `external_id` and serialized with sorted keys. Exclude export metadata
   such as the export timestamp from that hash. A changed draft, readback,
   release or corpus makes the affected evidence stale. Missing definitions or
   unverified results never count as completed checks. After an interruption following import, if
   the readback still matches, start at measurement, not import.
5. Hand off definitions and measured counts to the configuration owner. A native
   `quality.yaml` or Silver check must preserve the measured semantics and pass
   the applicable platform proof before it can become a platform rule. A TestGen
   severity or threshold grants no platform failure action or switch-on approval.
