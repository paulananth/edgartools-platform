# README architecture refresh: verification

Baseline: `origin/main` at `3eee39f2`, inspected 2026-10-15 ET.
Scope: documentation and rendered diagrams only. No source activation,
catalog publication, infrastructure change or runtime deployment performed.

## Factual reconciliation

| README explanation | Current repository evidence |
| --- | --- |
| Skills are operating guides with separate approval and activation | `skills/data-platform/SKILL.md`, `skills/data-onboarding/APPROVE.md`, `skills/refining-rules/SKILL.md` |
| Profiling identifies quality requirements, RDM needs and every part's silver fields | `skills/data-profiling/SKILL.md`, `skills/data-profiling/scripts/profiling/catalog.py`, `docs/specs/profiling/findings.md` |
| Catalog generation is one way, from files, and can describe drafts | `edgar_warehouse/rules/catalog.py:plan`, `publish`, `_profiles`; `edgar_warehouse/rules/cli.py:_catalog` |
| Profile-based silver/RDM catalog metadata is conditional on supplied summaries | No `rules/sources/*/profile.yaml` in this baseline; current plan has 13 tables and 8 lineage links. Catalog tests exercise profile-enabled plans. |
| Catalog quality requirements do not establish silver runtime enforcement | `skills/data-quality/SKILL.md`, especially its silver boundary |
| Identity binding, consolidation and field selection are separate | `CONTEXT.md`; `edgar_warehouse/mdm/clean/identity.py`, `merge.py`, `scope.py` |
| Merge proposals are rechecked under the lock; proposal and batch share a transaction | `MergeStage.apply`, `_check_rule_proposals`, `_execute`; migration 020 and Ticket 77 |
| Publication intent is atomic with master state; delivery is separate and verified | `edgar_warehouse/workers/mdm_merge.py`, `mdm_publish.py`; `skills/data-platform/SKILL.md` mastering section |
| Configured Company, Person and Security rules exist; source qualification is distinct from deployment | `rules/merge/kinds/{company,person,security}.yaml`; the Security rule records the approved 13F Identifier Contract proof |
| Rust/Python/database responsibility boundaries | `docs/architecture/runtime-responsibilities.md`, `edgar_warehouse/rules/source_engine.py`, `edgar_warehouse/mdm/clean/identity.py` |
| Configured capture and AWS/silver integrations remain separate boundaries | `docs/configured-capture.md`, Company `artifact.copy` target, `skills/data-onboarding/SKILL.md`, `infra/scripts/install.sh` |

## Validation

- 57 README relative paths and heading anchors resolve; code fences balance.
- Five operational command forms resolve through the actual CLI parser;
  `workers describe` executes successfully for `mdm.prepare`, `mdm.merge`
  and `mdm.publish`. `--help` is handled by the same parser.
- `catalog.plan()` runs locally and gives identical output on repetition.
  No catalog server or data provider contacted.
- `pytest --testmon tests/unit/test_rules_catalog.py`: 8 passed in 7.32 s.
  Used the existing Python environment without syncing dependencies, with a
  dedicated testmon cache. No runtime code changed.
- All three Mermaid diagrams rendered offline into SVG, PNG and Excalidraw
  through the bundled gstack renderer. PNG width: 1,950 pixels each.
- All Excalidraw scenes contain native boxes and arrows, no flattened image:
  platform 33 elements, mastering 26, catalog 21. All PNGs visually inspected.
- Missing pinned Playwright Chromium was restored to its user cache before
  rendering. A subgraph conversion issue was resolved by simplifying the
  platform layout into two independently labeled flows; final renders report
  no page errors.
- `git diff --check` passes; overlap guard passes against other runtimes.

## Standards

Dedicated Codex branch and worktree; edits are limited to README, its diagram
artifacts and this workstream. No secrets or source-data values added. Examples
are explicitly invented. No other runtime's source, skill or planning files
edited. Source qualification, activation, catalog population and deployment are
described separately. VERSION and CHANGELOG remain outside this documentation
task's scope.

## Spec

The README leads with executive outcomes, then provides architecture, component
ownership, a skills/handoff table, an invented mastering example, identity and
field semantics, publication/recovery, and catalog generation/lineage. It links
technical details rather than reproducing every installation or migration
procedure. Three diagrams replace the obsolete ECS/DuckDB depiction and explain
mastering and catalog publication individually.

## GoF

`gof-refactor-reviewer` is available and was applied to the inspected engine
boundaries, MergeStage/identity and catalog code plus recent history. Verdict:
leave the existing implementation. The Python facade over Rust, scoped merge
reads and plain-function catalog planner already express the needed boundaries;
this task provides no evidence that another abstraction would lower current
change cost. No runtime refactor proposed or performed.

## Learning → skill

None. This task explains existing contracts and corrects stale entry-point
documentation. No skill behavior or approval process changed.
