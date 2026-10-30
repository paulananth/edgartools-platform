# Restore the catalog for all configured entities and pipelines

Priority: 20, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/mastering-to-done/issues/19-restore-the-catalog-and-publish-person.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task
Status: claimed (Codex, 2026-10-30); expanded by the operator to all configured entities and pipelines.
Blocked by: none for metadata from existing configuration; missing source configuration remains a recorded coverage gap, not authority to activate sources.

## Question

1. **Bring back the local OpenMetadata stack.** Find where its compose file lives; it was not in the repo when removed on 2026-10-01. Either restore the catalog volumes from the 2026-10-02 backups, or start clean and republish. Starting clean is likely simpler, since `rules catalog` publishes everything from the rules.
2. **Republish with `rules catalog`.** Person, the link types and the quality checks must show; extend the publisher if links aren't covered yet.
3. **Regenerate the Mapping Documents** (`rules mapdoc`) for Person and the link sources.

Check in the catalog UI and in the generated spreadsheets that each new field and link type appears.

## Expanded scope (operator, 2026-10-30)

"complete for all entities and pipelines update the skills ... use the skills".
Restore and publish the catalog and Mapping Documents for every configured kind,
source, relationship and pipeline. Discover coverage from rules, with no fixed
entity/source list. Catalog publication does not activate or run source pipelines.

## Parts

- [x] Inventory every configured kind, source, relationship, source/pipeline target, quality rule and workbook — 2026-10-30 08:47 ET: 12 sources, four master kinds, 13 Dataset Contracts, 16 pinned relationship types/five capacities, 13 targets/68 tasks; 15 offline rules checks pass. Original 14 workbooks had no drift; two non-MDM sources, two standalone pipelines and relationship definitions needed documents.
- [x] Restore the documented local OpenMetadata stack without replacing volumes or disturbing shared stores — 2026-10-30 08:47 ET: existing Docker context restored, compose started the pinned server with bounded heaps; API reports version 2.0.2. An existing authorized ingestion bot is reused; no permissions were broadened.
- [x] Use existing catalog/mapdoc commands first; repair only demonstrated metadata gaps — 2026-10-30 08:47 ET: native pipeline definitions/tasks, pinned relationship metadata, complete quality descriptions, all-source/workflow workbooks and readback check added. Invented real-server tests exposed service-scope filtering, omitted task readback fields and bot-preserved descriptions; fixes retain the existing pure projection/callable transport seam. No source acquisition or processing.
- [x] Generate and check Mapping Documents for every configured entity, source, link and pipeline — 2026-10-30 08:47 ET: documented mapdoc write/check generated 19 documents; cell comparison passes, all 68 configured steps are represented, existing Notes preserved by retained tests.
- [ ] Qualify complete, deterministic catalog plan and repeat publication/readback for all configured entities/pipelines, relationship types, quality checks and lineage.
- [x] Test with invented metadata before publishing configured metadata, then reset only task-owned catalog metadata before deployment — 2026-10-30 08:39 ET: real API proof passed (three tables, one pipeline/two tasks, two lineage links, stale cleanup, drift/repair, unchanged versions); API reset removed two synthetic services and verified zero owned services remain. Accounts, volumes, shared stores and source records untouched.
- [ ] Verify catalog API readback and generated workbook cells; publish counts/outcomes only, retain private runtime details outside Git. The operator replaced UI inspection with API/CLI-only verification and prohibits computer use on this project (2026-10-30).
- [x] Complete Standards, Spec and GoF review — 2026-10-30 08:47 ET: two independent reviewers found no blocking issue, including narrow description PATCH ownership and foreign-identity refusal.
- [x] Publish implementation/evidence in PR #1242 — 2026-10-30 08:56 ET: source a0327237 is published and independently installed; final-head CI remains a separate readiness gate.
- [x] Qualify normal metadata CLI and all workbook contents from the installed five-wheel bundle outside the checkout — 2026-10-30 08:56 ET: committed source a0327237 passed in 137.43 seconds; catalog plan includes native pipelines/relationships, all bundled Mapping Documents pass check, missing catalog credentials refuse without a request. The subsequent CLI wording and parser checks passed 21 cases.
- [x] Require final-head CI before readiness — 2026-10-30 12:44 ET: #1242 head b7ffce65 passed all 20 checks, then merged as 778bf332. Configured metadata deployment still waits for the separately requested named quality-case capability and its invented proof/reset.
- [ ] Publish 18 configured contract checks and six Silver checks as named native quality test cases; retain five fixes as correction metadata and 43 profiling entries as proposals/evidence. Definitions only: no invented execution results (operator, 2026-10-30).
- [ ] Qualify native definitions/cases and logical-suite membership, unchanged repeat, drift/stale cleanup and exact ownership on invented metadata; repeat the task-owned reset before deployment.
- [ ] Create a native domain and glossary for each configured entity kind, with field/identifier/relationship terms, domain assignments and API coverage checks (operator, 2026-10-30).
- [ ] Replace opaque primary labels with configured business names and contextual definitions; prove the three reported filing-identifier examples and keep technical identities for lineage.
- [ ] Learning → skill: update reusable metadata coverage, publishing and verification guidance on a separate skill branch/PR.

## Initial GoF consult

The existing pure rules-to-plan projection and callable HTTP publishing boundary
have evolved through feed lineage, profile/Silver metadata and registered-column
coverage. Keep those tested seams. Add missing configured metadata to the existing
projection; no new registry, ingestion system or controller hierarchy is justified.

## Operator verification/reset rulings (2026-10-30)

Test with invented metadata first; reset task-owned catalog metadata only before deployment. Use the OpenMetadata API for deletion/reset and all inspection. Never use computer use on this project. This supersedes the original question's UI inspection step.

## Implementation qualification

The plan is 62 metadata tables, 37 lineage links, 13 pipeline targets/68 tasks,
and 19 Mapping Documents. These counts describe configured definitions, not
active source jobs. The 16 relationship types and five capacities come from the
policy-pinned reference data and its checked hash. No fixed entity/source list
was added. Pipeline metadata carries no asserted activation state or schedule.

The real invented API test passed in 2.12 seconds: three tables, one pipeline,
two tasks, two lineage links, stale table/pipeline cleanup, explicit remote drift,
repair and unchanged versions on replay. The reset removed its two task-owned
services and verified none remain. No configured metadata is deployed yet.

The source API requires explicit pipeline task fields on readback. Bot PUTs can
preserve nonempty descriptions: owned descriptions/column descriptions use
narrow JSON Patch after exact entity identity checks, preserving unrelated tags.
The normal catalog check reads back objects, membership, tasks and lineage,
without mutation. A nonzero result prevents a completion claim.

Affected runtime/metadata tests: the full cohort passed 45 cases before one
legacy fake failed to reach its intended table-identity check after service
identity validation was added. Correcting that fake (without weakening its
assertion), plus the complete current coverage file, passed 13 cases. The two
new PATCH-specific cases independently passed in the 12-case coverage run.
The 15 offline rules checks, actual mapdoc check and source compile/whitespace
checks pass. Final full CI remains a release gate.

## Named quality-case scope and GoF consult

The operator selected named quality test cases, definitions only. Keep engine
checks and decisions unchanged; do not translate them into guessed SQL or
invent execution results. Preserve every rule, failure action and configuration
reference. Do not promote profiling proposals into active checks. Use the native
catalog's external-test platform and logical grouping, with no execution schedule.

The existing pure planner/callable publishing seam remains appropriate. Native
quality entities use different global scopes and parent references from tables;
keep that bounded projection/reconciliation behind one owning helper rather
than growing a new engine, registry or class hierarchy. Preserve unrelated
quality objects, prevent recursive deletion of their dependencies, and verify
all native metadata through APIs only.

## Business catalog correction (2026-10-30 13:01 ET)

The base assets are now published: 62 tables, 13 pipelines, 37 lineage links.
Native Markdown descriptions are HTML-escaped at rest; a narrowly scoped
one-level decode now verifies every description without masking genuine changes.
Base API readback passes with zero differences. This correction has five
passing positive/negative encoding cases; no physical data was changed.

The operator requires entity domains, glossaries and understandable business
labels, not just technical paths and generic column labels. Keep those labels
and meanings in catalog configuration. Every configured kind must have a domain
and glossary; assets inherit only configured/declared associations. Preserve
technical names as identities, distinguish proposed profile assets from
registered definitions, and never invent business owners or approved glossary
status. Use APIs only.
