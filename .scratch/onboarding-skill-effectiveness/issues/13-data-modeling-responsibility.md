# data-modeling: Define one responsibility

Type: task
Status: open
Priority: P0
Blocked by: 01, 07
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-modeling](../../../skills/data-modeling/SKILL.md)
Step: 1 of 6
Skill dependencies: data-profiling
Applicability: Every new part whose class, identity, relationship or destination needs mapping.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Decide the part's class, kind, identifiers, relationship type and time model from findings and the existing business vocabulary.

Inventory existing instructions against the neighboring owners: data-onboarding and data-quality; data-catalog consumes the resulting meaning. Reconcile the current index and references before moving any text.

Start from skills/data-modeling/SKILL.md: Decision rules, Workflow, Prove the model on the data before building. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [data-profiling: Define one responsibility](./07-data-profiling-responsibility.md)

Priority rationale: Identity and destination decisions precede configuration.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] List decisions, inputs and outputs owned here using current repository evidence. Verified by reading the current `data-modeling` skill and REQUIREMENTS.md against `data-profiling`, `data-onboarding` (SKILL.md, MAP.md), `data-quality`, `refining-rules`, `data-catalog` and `mdm-engineering`; recorded in [Decisions, artifacts and handoffs](../../../skills/data-modeling/SKILL.md#decisions-artifacts-and-handoffs). (2026-11-20 18:27 ET)
- [x] Assign each overlapping responsibility one authoritative owner and a named handoff. Verified by checking each row against the owner's own text: profiling's Data Modeling row, `data-catalog` ("decides the class, the kind..." is Data Modeling's; the catalog projects), [Final exposable tables](../../../skills/data-platform/FINAL-TABLES.md) (onboarding records the selection) and data-quality's hard stops. The lints do not validate ownership. (2026-11-20 18:27 ET)
- [x] Point data-modeling's code-set hard stop at the owner that drafts RDM versions (Data Onboarding or Refining Rules, by [CODE-SETS.md](../../../skills/data-profiling/CODE-SETS.md)), deferred here by [07](./07-data-profiling-responsibility.md). Verified by reading the edited row against profiling's table row for RDM code set versions. (2026-11-20 18:27 ET)
- [x] Move the new-kind decision wording to Data Modeling, deferred here by [07](./07-data-profiling-responsibility.md): the three tests and their outcomes are decided in [2. A master part: its kind](../../../skills/data-modeling/SKILL.md#2-a-master-part-its-kind); profiling's "Identify an MDM kind" keeps the measurement and the draft in `findings.yaml` and points there. Verified by reading both sections and by grepping every inbound citation of "Identify an MDM kind" (data-onboarding SKILL.md and MAP.md, data-modeling) and `data-modeling/SKILL.md#` anchors, which still resolve to unchanged headings. (2026-11-20 18:27 ET)
- [ ] ~~Move CODE-SETS.md out of data-profiling~~ deferred to [19](./19-data-onboarding-responsibility.md): data-onboarding receives it; the hard stop already names the owner and links the file where it is.
- [ ] ~~Fix `data-operations`' readiness step that routes an RDM blocker "through data-profiling's RDM steps" (skills/data-operations/SKILL.md, "Operationalize every domain", step 3, RDM per domain)~~ deferred to [55](./55-data-operations-responsibility.md): that ticket owns data-operations; the owner it should name is Data Onboarding or Refining Rules.
- [ ] ~~Reconcile "one of `KINDS`" (data-modeling section 2, REQUIREMENTS.md) with profiling's "Nothing else holds a list of kinds" (`mdm-kinds`)~~ deferred to [14](./14-data-modeling-consistent-rules.md): `KINDS` in `edgar_warehouse/mdm/evidence.py` is read from a catalog, and which list is authoritative is a consistency question, not an ownership one.
- [ ] Demonstrate the boundary on a shared issued identifier, an ambiguous name, a cross-reference-only identifier and an effective-dated relationship; link retained work rather than duplicating it. A documented walkthrough is under `## Answer`. Nothing was executed: this ticket authorizes no scenario code, and a traced walkthrough is not proof on data.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. The focused checks are recorded under `## Answer`; nothing was committed or pushed and no PR exists.
- [ ] Learning → skill: proposed lesson: "Data Modeling decides from measurements it does not take; each test it decides on is measured by Data Profiling and each artifact written from its decision belongs to the owner in [Decisions, artifacts and handoffs](../../../skills/data-modeling/SKILL.md#decisions-artifacts-and-handoffs)". Stays unchecked until the change is published and reviewed.

## Answer

Data Modeling decides where one profiled part sits: its class, its kind or a
proposed new kind, which identifiers match and which are lookup only, the code
set and where each code field goes, a relationship's type, ends, capacity and
dates, a transaction or child part's key and links, business and recorded
time, the final outputs, and a Gold fact's shape. Its input is approved
findings; its output is the written decision and, when the decision changes
how records join or what a row is, the proof report of section 9. It measures
nothing, writes no configuration, check or code set version, and approves
nothing. Each neighbouring artifact has one owner and a named handoff in
[Decisions, artifacts and handoffs](../../../skills/data-modeling/SKILL.md#decisions-artifacts-and-handoffs),
which replaces the skill's earlier handoff list; REQUIREMENTS.md keeps scope
and refusals and points to the table.

What this branch reconciles:

- The code-set hard stop sent RDM drafts "through data-profiling's RDM
  steps", but profiling's table gives RDM code set versions to Data Onboarding
  or Refining Rules. The hard stop names them, and links CODE-SETS.md where it
  stays.
- The new-kind tests were worded as a decision in profiling. Data Modeling's
  section 2 holds the decision and its outcomes (a role, a detail, silver, a
  code set, or a proposed kind for the operator); profiling's "Identify an
  MDM kind" keeps the three measurements and the draft in `findings.yaml`.
  The section name is unchanged, so the citations in data-onboarding
  (SKILL.md, MAP.md) still resolve.

Documented boundary walkthrough (not executed; each case traced to current
text, with the retained work linked rather than restated):

| Case | Profiling measures | Data Modeling decides | Next owner and artifact |
|---|---|---|---|
| Shared issued identifier (one value carried by records of two sources) | `identifiers.pairs`, the repeat and clash counts | Matching, only if the kind's Identifier Contract declares the namespace, at the level every source carries ([section 3](../../../skills/data-modeling/SKILL.md#3-identity-or-cross-reference); worked case in [security-master, Keys and identifiers](../../../skills/security-master/SKILL.md#keys-and-identifiers)); a new namespace is the operator's | Data Onboarding writes the contract; MDM Engineering's [cross-reference completion](../../../skills/mdm-engineering/CROSS-REFERENCE.md) builds the lookup |
| Ambiguous name (no identifier in either source) | The name-id measurements in [NAME-IDS.md](../../../skills/data-profiling/NAME-IDS.md) | An id from the name is the last resort and a cross-reference (section 3, "No identifier at all"); similar names never merge (Hard stops) | Data Onboarding or Refining Rules, with the operator, sets the matching rule (profiling's table) |
| Cross-reference-only identifier (one value on two masters) | The count of values given to two or more masters, and each clash's names and types | Lookup only: it finds records and never joins them (section 3, "Lookup only", "Read a clash") | Data Onboarding maps it under the contract's `cross_references`; a clash that needs a check goes to Data Quality |
| Effective-dated relationship | Time roles (`time.as_of`, `time.as_at`) and the stated date fields | The type (existing or inverse first), its ends, capacity, `valid_from` / `valid_to` sources, `keeps_start`, `ends_parent_links` ([section 5](../../../skills/data-modeling/SKILL.md#5-a-relationship-its-type), [section 7](../../../skills/data-modeling/SKILL.md#7-time)) | Data Onboarding drafts a new type in `mdm-relationship-types`; an unknown business start under an approved file date is Data Quality's [Approved provisional dates](../../../skills/data-quality/SKILL.md#approved-provisional-dates) |

Baseline: `HEAD` and `origin/main` are both
`30ae0e7b631df6db9d9560f7da3cb6a1cbe4f4d9`. The prerequisite skill changes
are on `origin/main`: ticket 01 as `f8233ff2` (PR #1956) and its record as
`c6bca06e` (PR #1967), ticket 07's skill change as `6c5c5393` (PR #1969).
Ticket 07's own Status line still reads open; its closeout is separate, and
this branch does not edit it.

Installed provenance was not verified on this branch: reading
`~/.agents/skills/write-skill/SKILL.md` was denied, and listing or resolving
`~/.agents/skills/data-modeling` and `~/.claude/skills/data-modeling` was
refused outside the worktree. The installed write-skill guidance was therefore
not read, and no installed copy was read or changed.

Checks run for this change: `uv run --no-project --with pytest -- pytest -q
-p no:cacheprovider tests/unit/test_skills_cite_no_ticket.py
tests/unit/test_profiling_genericity.py
tests/unit/test_guides_name_existing_paths.py` — **149 passed**;
`git diff --check` — clean; `skills/data-modeling/SKILL.md` — 470 lines.
`bash scripts/dev/overlap_guard.sh` exited 1 on the unstamped `2026-11-20 18:27 ET`
stamps, which `commit_push.sh` fills, so the overlap with other open work was
not evaluated. These checks cover genericity, cited-path existence, ticket
numbers in skills, skill file length and whitespace; they do not validate
ownership, section anchors or routing behaviour.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
