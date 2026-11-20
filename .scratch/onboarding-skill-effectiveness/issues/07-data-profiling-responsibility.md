# data-profiling: Define one responsibility

Type: task
Status: resolved
Priority: P0
Blocked by: 01
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-profiling](../../../skills/data-profiling/SKILL.md)
Step: 1 of 6
Skill dependencies: data-platform
Applicability: Every new captured dataset; compare mode only when an approved delivery changes.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Measure the local captured data once and emit reusable evidence; do not choose final model semantics or run a load.

Inventory existing instructions against the neighboring owners: data-modeling, data-quality and data-onboarding. Reconcile the current index and references before moving any text.

Start from skills/data-profiling/SKILL.md: Modes, Profile once, How to work, Compare a new delivery. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md)

Priority rationale: Reusable evidence is the input to every source model.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] List decisions, inputs and outputs owned here using current repository evidence. Verified by reading the current `data-profiling` skill, its scripts (`profiling/hierarchy.py` writes each invalid row's proposed `fix` and `needs_steward`) and the neighbouring `data-modeling`, `data-quality`, `data-onboarding`, `refining-rules`, `mdm-engineering` and `data-platform` instructions; recorded in [Decisions, artifacts and handoffs](../../../skills/data-profiling/SKILL.md#decisions-artifacts-and-handoffs). (2026-11-20 18:11 ET)
- [x] Assign each overlapping responsibility one authoritative owner and a named handoff. Verified by reviewing the table's rows against the cited owner sections and the inbound links to this skill (`#exposure-tags-follow-requirements-and-mappings`, `#choose-a-proof-sample-by-kind`, `#tell-the-discovery-story-as-you-work`, `#modes`, which still resolve). Data Platform's Data Profiling row agrees with it. The lints do not validate ownership. (2026-11-20 18:11 ET)
- [x] Demonstrate the boundary on a multi-part archive with two encodings, repeated issued identifiers, an unreadable member and a changed delivery; link retained work rather than duplicating it. Verified by the documented walkthrough under `## Answer`. No source was profiled, and `compare` was not run. (2026-11-20 18:11 ET)
- [x] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. PR #1969 squash-merged at 2026-11-20 18:02 ET as `6c5c5393800e7e83ae59fec1342ab2760e3dbdd5`. Its updated-head CI passed 12 checks. (2026-11-20 18:11 ET)
- [x] Move the RDM code-set procedure is not this ticket's change. Carried by [19](./19-data-onboarding-responsibility.md) and [13](./13-data-modeling-responsibility.md); the procedure stays in [CODE-SETS.md](../../../skills/data-profiling/CODE-SETS.md) until those tickets move it. (2026-11-20 18:11 ET)
- [x] Move the new-kind decision wording is not this ticket's change. Carried by [13](./13-data-modeling-responsibility.md). Profiling keeps the measurement tests. (2026-11-20 18:11 ET)
- [x] Learning → skill: measurement and the evidence files stay in Data Profiling; every decision made from them goes to the owner named in [Decisions, artifacts and handoffs](../../../skills/data-profiling/SKILL.md#decisions-artifacts-and-handoffs). (2026-11-20 18:11 ET)

## Answer

Data Profiling measures the local captured copies once and writes reusable
evidence: `findings.yaml`, `REPORT.md`, `invalid_rows.jsonl`,
`fingerprints.json` and, for a changed delivery, `drift.yaml`. It records the
operator's approval of those findings in their exact words. It owns the
`catalog` generator and the measurements behind source ranking and name ids.
It does not decide the final model, write configuration, publish the catalog
or RDM, decide checks or run a load. Each of those has one owner and a named
handoff in [Decisions, artifacts and handoffs](../../../skills/data-profiling/SKILL.md#decisions-artifacts-and-handoffs).

What this branch reconciles:

- Writing and publishing the catalog summary right after approval
  conflicted with the `catalog` mode and with `data-onboarding`'s
  **plan-parts**, which write it only once a part lands in silver. The
  catalog summary and its timing now belong to `data-onboarding`. Profiling's
  hand-over step points there.
- The part-ordering text duplicated `data-onboarding`'s **plan-parts**. It is
  replaced by a pointer to the table.
- The exposure section duplicated
  [Final exposable tables](../../../skills/data-platform/FINAL-TABLES.md) and
  `data-modeling`'s "Final outputs and exposure". Profiling keeps only its
  evidence trace. Two review-checkpoint rules that existed only in profiling
  (what to show for each table, and that an approval without the table list
  does not approve exposure) go to `FINAL-TABLES.md`.
- "Fix in the mapping" names the mapping's owner (`data-onboarding` **map**,
  or `refining-rules` for a live feed).

Documented boundary walkthrough (not executed; each case traced to the
skill's current text):

| Case | Profiling's evidence | Retained artifact and next owner |
|---|---|---|
| Multi-part archive | Each zip member of CSV or Parquet is its own input; a readme or metadata file goes under `dataset.not_read` ("Formats") | `findings.yaml` parts, read by `data-onboarding` **discover** |
| Two encodings | A CSV that is not UTF-8 is read as Windows-1252, else Latin-1, with `encoding` marked inferred and the first non-UTF-8 byte; `declare` gives `read.encoding` ("Unreadable tables") | The reading contract's encoding, written by `data-onboarding` **map** |
| Repeated issued identifiers | `entities` derives a part keyed by the repeating identifier; `identifiers.pairs` gives how identifiers pair ("Modes", "Reading the findings") | `data-modeling` decides which identifiers decide identity; the data is not scanned again |
| Unreadable member | Listed under `dataset.not_read` with its reason; the rest is profiled and reported ("Unreadable tables") | The report names it; a reader gap is a profiler fix used on the next source |
| Changed delivery | `compare` against the approved findings writes `drift.yaml`, with each item naming its skill ("Compare a new delivery") | `refining-rules` decides changes; the approved findings stay as they are and are not profiled again |

Baseline: `HEAD` and `origin/main` are both
`f8233ff25e6e61933568121d8fa5dd6e883e0862`, ticket 01's squash merge (PR
#1956); the commit is on `origin/main`. The installed
`~/.agents/skills/data-profiling` and `~/.claude/skills/data-profiling` both
resolve to `/Users/aneenaananth/projects/edgartools-platform/skills/data-profiling`,
a separate checkout. Its skill file is modified there and differs from this
worktree's skill; neither the installed copy nor that checkout was changed.
The installed `write-skill` guidance was read. Its skill-bill command resolves
the installed copy, so its size is not evidence for this worktree's skill.

Checks run for this change: `uv run --no-project --with pytest -- pytest -q
-p no:cacheprovider tests/unit/test_profiling_genericity.py
tests/unit/test_guides_name_existing_paths.py` — **143 passed**;
`git diff --check` — clean; `skills/data-profiling/SKILL.md` — 455 lines
(31,992 bytes). These checks cover genericity, cited-path existence and
whitespace; they do not validate ownership or routing behaviour.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
