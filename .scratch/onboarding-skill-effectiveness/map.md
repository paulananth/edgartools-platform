# Make source-onboarding skills effective

Type: map
Status: open
Labels: wayfinder:map

## Destination

Improve every skill used to onboard a source through six outcomes: one responsibility, consistent shared rules, a short executable entrypoint, resumable progress, generic behavioral verification and measured effectiveness. Completion means each applicable phase has evidence of a clearer, reliable handoff and measured task outcomes.

## Notes

The operator requested six tickets for each skill in source-onboarding scope. This map contains **96 open child tickets across 16 skills**, six per skill. It follows the repository's [local Markdown tracker](../../docs/agents/issue-tracker.md); these files are the tickets, not GitHub issues.

Execution override: the operator explicitly requested the six improvement steps as tickets. These are implementation and investigation tasks, not a request to resolve the whole map now. Resolve one ticket per session, on its own fresh branch and PR. Creating this map does not authorize source activation, provider acquisition, access changes or deployment.

Consult the invoked Wayfinder skill, [CLAUDE.md](../../CLAUDE.md), the [skills index](../../skills/README.md), and the child ticket's own skill at execution time. Installed and repository skill copies have already shown different content; identify the actual entrypoint being exercised before judging effectiveness.

### Scope

| Skill | Priority | Depends on skills | When it participates |
| --- | --- | --- | --- |
| [data-platform](../../skills/data-platform/SKILL.md) | P0 | None | Every source: route the work and discover configured connections. |
| [data-profiling](../../skills/data-profiling/SKILL.md) | P0 | [data-platform](../../skills/data-platform/SKILL.md) | Every new captured dataset; compare mode only when an approved delivery changes. |
| [data-modeling](../../skills/data-modeling/SKILL.md) | P0 | [data-profiling](../../skills/data-profiling/SKILL.md) | Every new part whose class, identity, relationship or destination needs mapping. |
| [data-onboarding](../../skills/data-onboarding/SKILL.md) | P0 | [data-modeling](../../skills/data-modeling/SKILL.md), [data-quality](../../skills/data-quality/SKILL.md) | Every new source or new kind; live-source revisions route to refining-rules. |
| [data-quality](../../skills/data-quality/SKILL.md) | P0 | [data-profiling](../../skills/data-profiling/SKILL.md), [data-modeling](../../skills/data-modeling/SKILL.md) | Every source with field constraints, defects or downstream quality obligations. |
| [refining-rules](../../skills/refining-rules/SKILL.md) | P2 | [data-onboarding](../../skills/data-onboarding/SKILL.md), [data-quality](../../skills/data-quality/SKILL.md) | Conditional: the proposed onboarding work changes an existing source or matching policy. |
| [mdm-engineering](../../skills/mdm-engineering/SKILL.md) | P2 | [data-modeling](../../skills/data-modeling/SKILL.md) | Conditional: choose mastering proof or investigate a demonstrated engine or storage gap; configuration remains the default. |
| [bookkeeping](../../skills/bookkeeping/SKILL.md) | P1 | [data-onboarding](../../skills/data-onboarding/SKILL.md) | Every source's declared execution targets; honor the target's configured grain. |
| [change-journal](../../skills/change-journal/SKILL.md) | P1 | [bookkeeping](../../skills/bookkeeping/SKILL.md) | Every source whose processing or publication produces journal events and delivery receipts. |
| [data-operations](../../skills/data-operations/SKILL.md) | P1 | [data-onboarding](../../skills/data-onboarding/SKILL.md), [bookkeeping](../../skills/bookkeeping/SKILL.md), [change-journal](../../skills/change-journal/SKILL.md) | Every local source qualification and operational load; hosted actions require applicable authorization. |
| [data-governance](../../skills/data-governance/SKILL.md) | P1 | [data-modeling](../../skills/data-modeling/SKILL.md) | Every source's governed outputs and lineage claims. |
| [data-catalog](../../skills/data-catalog/SKILL.md) | P1 | [data-governance](../../skills/data-governance/SKILL.md), [data-onboarding](../../skills/data-onboarding/SKILL.md), [data-quality](../../skills/data-quality/SKILL.md) | Every source's business metadata and steward-facing publication. |
| [openmetadata](../../skills/openmetadata/SKILL.md) | P2 | [data-catalog](../../skills/data-catalog/SKILL.md) | Conditional: OpenMetadata is the configured catalog destination. |
| [access-audit](../../skills/access-audit/SKILL.md) | P1 | [data-platform](../../skills/data-platform/SKILL.md) | Review the skill or access changes being finalized; run only applicable read-only platform checks. |
| [pipeline-orchestration](../../skills/pipeline-orchestration/SKILL.md) | P3 | [data-operations](../../skills/data-operations/SKILL.md), [bookkeeping](../../skills/bookkeeping/SKILL.md), [change-journal](../../skills/change-journal/SKILL.md) | Conditional: onboarding includes a recurring timer, dependency sequence or start/stop deployment. |
| [aws-snowflake-operations](../../skills/aws-snowflake-operations/SKILL.md) | P3 | [data-operations](../../skills/data-operations/SKILL.md), [access-audit](../../skills/access-audit/SKILL.md) | Conditional: onboarding touches AWS, Snowflake, hosted connections, images or deployment. |

Conditional skills receive the same six improvement tickets, but an individual source uses them only when the applicability condition holds. This prevents a local onboarding from requiring deployment or scheduling solely to finish a checklist.

### Six outcomes

1. Define one responsibility: establish ownership, inputs, outputs and handoffs.
2. Reconcile shared rules: resolve duplicate or contradictory instructions against the authoritative policy, preserving operator decisions.
3. Make the entrypoint executable: keep required actions and stop conditions close; route optional detail to discoverable references.
4. Make progress resumable: reuse one common onboarding record with artifact, version and invalidation evidence.
5. Specify generic verification: reuse configured engines and shared harnesses, with source-provided invented fixtures and observable expected outcomes.
6. Measure effectiveness: compare representative task outcomes with a baseline, including repeated work, questions, failures and elapsed time.

### Priority and dependency policy

- **P0 — source-building foundation:** data-platform, data-profiling, data-modeling, data-quality and data-onboarding. Establish reusable evidence and a configured source first.
- **P1 — operational and governed completion:** bookkeeping, change-journal, data-operations, data-governance, data-catalog and access-audit. These are required completion concerns where applicable, not optional polish.
- **P2 — conditional specialist paths:** refining-rules, mdm-engineering and openmetadata. Promote an applicable ticket when it blocks the selected source.
- **P3 — recurring and hosted expansion:** pipeline-orchestration and aws-snowflake-operations. Promote them when the selected source explicitly requires scheduling or hosted delivery; this rank does not make an applicable safety or access check optional.

Among open, unblocked, unclaimed tickets, take the highest priority first (P0 before P1 before P2 before P3), then the lowest ticket number. Dependencies always override priority; a promoted downstream ticket brings its unresolved prerequisites with it. Rank is backlog urgency, not runtime source sequence or permission.

Each ticket depends on its preceding step, the matching data-platform step and the matching step of the upstream skills in the table. For example, the onboarding entrypoint waits for the modeling and quality entrypoints; it does not wait for all six upstream improvements to finish. The first frontier remains the ownership ticket for data-platform. Independent unblocked branches can advance separately.

The table describes dependencies between **improvement tracks**, not a literal operational command sequence. Quality checks consume mapped fields during real onboarding; the table's quality-to-onboarding edge makes the quality skill contract clear before the onboarding skill integrates it. Change Journal remains independent even though its improvement examples consume Bookkeeping's producer evidence. Hosted work consumes data-operations' local qualification guidance, not a completed hosted load. Access audit remains a cross-cutting finalization gate for applicable changes and is not postponed until P3.

`Priority:`, `Skill dependencies:` and `Blocked by:` in the child files record urgency, upstream ownership and concrete blockers respectively. The child blockers are authoritative; do not infer readiness from priority or maintain another open-ticket list.

No scenario or test code is approved by creating these tickets. Proposed Given–When–Then scenarios must receive the operator's required approval before implementation. Local checks remain bounded and affected-only; CI runs the full suite. Longer user journeys and failure transitions take priority over trivial or repeated tests.

### Existing work to preserve

- [The data-onboarding skill is split behind pointers](../rebuild-priorities/issues/215-split-the-data-onboarding-skill.md) already records a completed split. Review the current entrypoint and installed copy before proposing more moves.
- [Move the business-meaning passages out of the openmetadata skill](../catalog-skill-routing/issues/02-move-business-meaning-out-of-the-openmetadata-skill.md) already owns specific catalog responsibility moves. Consume that work or link the overlap; do not implement it twice.
- The private-fund onboarding and its pending local proof remain in their existing worktree and ticket. This map does not claim that source is onboarded.

## Decisions so far

- [data-platform: Define one responsibility](issues/01-data-platform-responsibility.md): Data Platform owns the next-phase decision, shared source-readiness acceptance, and connection discovery/setup. Downstream procedures stay with their owning skill. PR #1956, merged 2026-11-20 17:07 ET.
- [data-platform: Reconcile shared rules](issues/02-data-platform-consistent-rules.md): a rule list names each rule's home and grants no permission. The findings-approval conflict is carried by tickets 08 and 20. PR #1966, merged 2026-11-20 17:46 ET.
- [data-profiling: Define one responsibility](issues/07-data-profiling-responsibility.md): profiling owns measurement and the evidence files. Decisions made from them belong to their named owners. PR #1969, merged 2026-11-20 18:02 ET.
- [access-audit: Define one responsibility](issues/79-access-audit-responsibility.md): the auditor owns the grade and the re-run. The fix belongs to the platform's operations skill. PR #1968, merged 2026-11-20 18:08 ET.
- [data-profiling: Resume a source's work](issues/10-data-profiling-resume.md): reuse only matching source, profiler, settings and artifact identities; record the first unfinished action in the shared source log. PR #1986, merged 2026-11-21 06:51 ET.
- [data-modeling: Decide one part](issues/15-data-modeling-entrypoint.md): make one model decision from approved findings, then hand configuration to its owner. PR #1985, merged 2026-11-20 20:04 ET.
- [data-modeling: Make progress resumable](issues/16-data-modeling-resume.md): keep part decisions and supporting findings in the shared source log; reuse only matching evidence, reopen affected downstream handoffs, and block missing approvals. PR #2027.
- [mdm-engineering: Define one responsibility](issues/37-mdm-engineering-responsibility.md): MDM Engineering owns reusable merge, storage, adapter and migration behavior. PR #1981, merged 2026-11-20 19:44 ET.
- [mdm-engineering: Reconcile shared rules](issues/38-mdm-engineering-consistent-rules.md): shared rules name their authoritative home; MDM Engineering keeps engine qualification and proof. PR #1987, merged 2026-11-21 06:57 ET.
- [data-governance: Define one responsibility](issues/61-data-governance-responsibility.md): Governance owns the evidence-backed neutral lineage path; catalog meaning and destination mechanics stay with their owners. PR #1982, merged 2026-11-20 19:49 ET.
- [data-governance: Reconcile shared rules](issues/62-data-governance-consistent-rules.md): unsupported lineage edges and missing evidence remain explicit gaps, not claims. PR #1988, merged 2026-11-21 07:02 ET.
- [data-platform: Specify generic verification](issues/05-data-platform-generic-verification.md): the three approved scenarios revealed no executable generic route; the capability gap is tracked separately and no behavior is claimed. PR #1983, merged 2026-11-21 07:33 ET.

- [data-profiling: Make the entrypoint executable](issues/09-data-profiling-entrypoint.md): the repository skill now has a supported profiling entrypoint; its implementation and evidence are captured in [Ticket 09: add the data-profiling entrypoint](https://github.com/paulananth/edgartools-platform/pull/1980).
- [Capability gap: the profiler reads some numbers through floating point](issues/gap-data-profiling-exact-numbers.md): exact decimal scale and long integer identifiers now survive through the generic reader; invented regression tests and the affected checks pass, in [fix(data-profiling): preserve exact numeric values](https://github.com/paulananth/edgartools-platform/pull/2015).
- [Capability gap: the data-platform route is not executable](issues/gap-data-platform-route.md): Added a source-neutral route command over configuration and retained resume evidence; conflicting change signals stop for operator clarification.
- [data-quality: Reconcile shared rules](issues/26-data-quality-consistent-rules.md): Shared approval and access gates stay with their authoritative owners; Data Quality owns check/fix meaning, measured counts and row dispositions.
- [data-quality: Make the entrypoint executable](issues/27-data-quality-entrypoint.md): A concise Start here route covers new/live MDM checks, silver specs, audits, supported commands, owners and stops.
- [data-profiling: Measure effectiveness](issues/12-data-profiling-effectiveness.md): The revised CLI improved exact inference and protected approved findings; the matched comparison does not isolate skill wording.
- [data-modeling: Specify generic verification](issues/17-data-modeling-generic-verification.md): Invented fixtures proved shared identity, ambiguous-name review, lookup-only separation, stated relationship periods and Silver fact ownership.
- [data-modeling: Measure effectiveness](issues/18-data-modeling-effectiveness.md): Revised guidance prompted fewer unsupported assumptions and proposed remaps, but final handoffs tied and the timing bar was missed.
- [data-modeling: Distinguish Silver source keys from resolved master IDs](issues/97-data-modeling-silver-link.md): Source-key facts store the key; readers resolve the master ID through `silver.master_binding`.
- [data-quality: Make progress resumable](issues/28-data-quality-resume.md): Shared source logs resume draft TestGen checks and reuse measurements only when the rule and corpus evidence matches.

## Not yet specified

- Exact numerical effectiveness targets, after each skill's baseline is measured.
- Capability gaps that generic verification exposes; each becomes a separate implementation ticket only when demonstrated.
- Additional domain or catalog adapters if a concrete source requires them.

## Out of scope

- Resolving the 96 child tickets in this charting session.
- Changing source rules, running data loads or completing the separate private-fund onboarding.
- Domain-specific overlays such as security-master and company-financials without a source requirement.
- AutoOntology, Gold, dashboards and consumer products downstream of the source-onboarding destination.
- General software design and SQL implementation skills unless an actual capability gap requires separate code work.
- Production-support and database-monitoring incident workflows unless onboarding encounters such an incident.

## Priority and dependency update

- [x] Add a priority and upstream skill dependencies to all 96 tickets and the 16-skill scope table (2026-11-20 06:48 ET).
- [x] Verify all priorities and 308 dependency edges; 564 links resolve, no cycles or priority inversions, and the documentation genericity check passes 144 tests (2026-11-20 06:48 ET).
- [x] Learning → skill: none; this update orders planned improvements without changing an operating skill (2026-11-20 06:48 ET).

## Charting record

- [x] Create six individually scoped tickets for each of the 16 skills, with applicability, dependencies and acceptance evidence; verified 96 open children (2026-11-20 06:44 ET).
- [x] Verify ticket counts, references, checklist structure and an acyclic dependency graph; 401 links resolve and the initial frontier contains one ticket (2026-11-20 06:44 ET).
- [x] Run the documentation-only genericity check; 144 passed (2026-11-20 06:44 ET).
- [x] Learning → skill: none; this session charts existing improvement proposals and does not validate a new operating practice (2026-11-20 06:44 ET).
