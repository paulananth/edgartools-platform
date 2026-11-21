# data-onboarding: Define one responsibility

Type: task
Status: open
Priority: P0
Blocked by: 01, 13, 25
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-onboarding](../../../skills/data-onboarding/SKILL.md)
Step: 1 of 6
Skill dependencies: data-modeling, data-quality
Applicability: Every new source or new kind; live-source revisions route to refining-rules.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Turn the modeled parts into configured readers, Dataset Contracts, quality mappings, target declarations and steward artifacts.

Inventory existing instructions against the neighboring owners: bookkeeping for execution and data-operations for the local proof and operational handoff. Reconcile the current index and references before moving any text.

Start from skills/data-onboarding/SKILL.md: Modes in order, The files are the rules, metadata, check and load; MAP.md and TARGETS.md. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

The prior split is recorded in [The data-onboarding skill is split behind pointers](../../rebuild-priorities/issues/215-split-the-data-onboarding-skill.md); inspect current references before repeating it.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [data-modeling: Define one responsibility](./13-data-modeling-responsibility.md); [data-quality: Define one responsibility](./25-data-quality-responsibility.md)

Priority rationale: A complete configured source is the primary deliverable.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] List decisions, inputs and outputs owned here using current repository evidence; recorded in [Decisions, artifacts and handoffs](../../../skills/data-onboarding/SKILL.md#decisions-artifacts-and-handoffs), checked against Data Platform, Data Modeling, Data Quality, Bookkeeping, Data Operations, Refining Rules and Data Catalog ownership sections. (2026-11-20 20:03 ET)
- [x] Assign each overlapping responsibility one authoritative owner and a named handoff; verified by reviewing the owner and handoff columns against each named skill's current instructions. This is a document review, not behavioral proof. (2026-11-20 20:03 ET)
- [ ] Demonstrate the boundary on a multi-part source with master, reference and transaction parts, then an interrupted configuration build; link retained work rather than duplicating it. Retained traces: [N-PORT parts](../../rebuild-priorities/issues/79-onboard-funds-and-securities-with-the-skills.md), [OpenFIGI reference/RDM and silver parts](../../rebuild-priorities/issues/80-onboard-openfigi.md), and [the retained part ordering](../../rebuild-priorities/issues/87-profiling-names-quality-rdm-silver-in-the-catalog.md). The interrupted build is visible in the [N-CEN onboarding log](../../onboarding/sec.ncen/onboarding-log.md), where later parts remain blocked on unresolved decisions. No retained single source demonstrates all three part classes, and no load or scenario was run here.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [x] Learning → skill: each onboarding artifact has one decision owner and an explicit handoff to its producer or next phase; recorded in [Decisions, artifacts and handoffs](../../../skills/data-onboarding/SKILL.md#decisions-artifacts-and-handoffs). (2026-11-20 20:03 ET)

## Answer

Data Onboarding owns the configuration that turns approved findings and
Data Modeling's decisions into source readers, Dataset Contracts, quality
mappings, target declarations, silver specs and steward artifacts. Data
Profiling supplies measurements and approved findings; Data Modeling supplies
part semantics; Data Quality owns check meaning, counts and dispositions;
Data Catalog owns business definitions and publication. Bookkeeping owns the
`bookkeeping` execution section and run-control semantics. Data Operations
owns initial local proof, loads and the operational handoff. Refining Rules
owns changes to an already configured source. The authoritative artifact and
handoff list is in [the skill's owner table](../../../skills/data-onboarding/SKILL.md#decisions-artifacts-and-handoffs).

The retained work demonstrates pieces of this boundary without repeating
them. Ticket 79 records the N-PORT Security, registrant and Fund master parts
and the HOLDS transaction rows. Ticket 80 records OpenFIGI's RDM reference
lists and silver listings that link to Security masters. Ticket 87 records
the intended master → reference → transaction ordering. The N-CEN log retains
a configuration build stopped at its unresolved CRD normalization decision;
it shows which part remains blocked, not a behavioral resume test. These are
related retained examples, not evidence that one source run proves the full
three-class boundary. That acceptance item remains open until a qualifying
retained source case can be linked.

Baseline and provenance: `HEAD` and `origin/main` are
`d650395c6d00b9adcf76d3afe890541afb280f14`. Prerequisite commits #1956
(ticket 01), #1971 (ticket 13), and #1984 (ticket 25) are ancestors of
`origin/main`; ticket 25's merge commit is the current head. The installed
`data-onboarding` links resolve to `/Users/aneenaananth/projects/edgartools-platform`,
at `3884e81b9cf5edc542e0395115b2784a9420076d`. The installed skill hash
matches that checkout's `HEAD`
(`a9e1ae2bdd882c028177910e554681b4a8a4bcff013f4715cf98a62ead094e01`) and
differs from this checkout's
(`deb669176e4da7100f63d6e9bbaf7e27661564148f2eeb29e66cc159e7c0332b`); the
skill and link script have no local status changes there.
The installed copy was read for provenance and was not changed. The installed
`write-skill` guidance was read; its edit ladder says to replace existing
guidance before appending and to place each fact at the lowest level that
reaches the reader in time.

## Validation and remaining work

- `UV_CACHE_DIR=/private/tmp/task19-uv-cache uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py` — **142 passed**. This checks skill/spec genericity; it does not exercise routing, ownership or resume behavior.
- `git diff --check` — clean.
- `skills/data-onboarding/SKILL.md` — 499 lines, below the repository's 500-line limit.

No source load, scenario test, commit, push or PR was performed. Publication
remains unchecked because this task explicitly prohibits commits, pushes and
PR creation. The three-class source demonstration remains unchecked because
current retained records do not show that complete case in one source.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
