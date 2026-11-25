# data-modeling: Measure effectiveness

Type: task
Status: resolved
Priority: P0
Blocked by: 06, 12, 17
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-modeling](../../../skills/data-modeling/SKILL.md)
Step: 6 of 6
Skill dependencies: data-profiling
Applicability: Every new part whose class, identity, relationship or destination needs mapping.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a shared issued identifier, an ambiguous name, a cross-reference-only identifier and an effective-dated relationship. Measure unsupported modeling assumptions, reopened decisions, downstream remapping and time to an evidence-backed model. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/data-modeling/SKILL.md: Decision rules, Workflow, Prove the model on the data before building. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Measure effectiveness](./06-data-platform-effectiveness.md); [data-profiling: Measure effectiveness](./12-data-profiling-effectiveness.md); [data-modeling: Specify generic verification](./17-data-modeling-generic-verification.md)

Priority rationale: Identity and destination decisions precede configuration.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Record the baseline, matched inputs and predeclared outcome and timing bars in [Comparison protocol](#comparison-protocol) before running the comparison. (2026-11-24 22:19 ET)
- [x] Run four matched pairs of two-wave decisions, with the same model and evidence in each pair; all sixteen CLI calls completed. Report elapsed time and unavailable live evidence under [Answer](#answer). (2026-11-24 22:19 ET)
- [x] Score against the approved behavior before revealing the revision labels. Record gains, regressions, missed bars and the shared Silver handoff error under [Answer](#answer). (2026-11-24 22:19 ET)
- [x] Publish the comparison in [docs(modeling): record paired effectiveness trials](https://github.com/paulananth/edgartools-platform/pull/2129); documentation genericity **155 passed**. (2026-11-24 22:20 ET)
- [x] Learning → skill: both revisions misread the stored Silver link. [Distinguish Silver source keys from resolved master IDs](./97-data-modeling-silver-link.md) owns the scoped clarification in Data Modeling's class guidance. (2026-11-24 22:19 ET)

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

## Comparison protocol

- Baseline: repository commit `d650395c6d00b9adcf76d3afe890541afb280f14`, immediately before the modeling entrypoint merge, `SKILL.md` blob `97ff51ff5a2a9a5b80253a383fecff04f22b673d`. Revised: `1810996d5bb39dc2b3c298b37cc09bea662e62cf`, blob `797263c0056f455447d14b002c227152d0380491`. Run with one fixed Claude Code release, Opus selection and low effort for both revisions. Neither installed copy is available.
- One paired trial per scenario, using the [verified modeling scenarios](./17-data-modeling-generic-verification.md#approved-scenarios) as the answer key. Both arms get the same invented evidence in two waves and the full pinned `SKILL.md`; only the skill text changes. No tools, live sources, operator wait, or actual configuration writes. Each wave starts a fresh CLI process; wave two receives the first answer and the new evidence. Compare the models' decisions, not the engine's test timing.
- Score before looking at revision labels. **Unsupported assumptions:** a definitive decision on the contested field before its evidence arrives, an incorrect final decision, or a factual premise contradicted or not supported by the evidence. **Reopened decision:** an initially definitive contested choice later changed or withdrawn; resolving an explicitly pending choice does not count. **Downstream remapping:** a change to a mapping marked ready for handoff in wave one, including withdrawal; this measures proposed rework, not production remaps. Count at most one per contested choice per metric; score independent relationship and fact decisions separately.
- **Time to evidence-backed model:** sum both CLI elapsed times when the final answer passes the answer key and cites the supplied evidence; exclude fixture preparation and time between calls. Includes startup and model-service wait that the CLI cannot separately attribute; no operator or source wait. Compare only paired correct outcomes.
- Revised acceptance bars: four supported final decisions out of four, zero unsupported assumptions, zero reopened decisions, zero remaps, and no comparable scenario more than 10% slower than baseline. Keep correct decisions regardless of timing; report any misses without inferring a revision effect from a single observation per case. No automatic retry, model fallback, or extra billed run for a refused trial.

| Scenario | Wave one: contested evidence withheld | Wave two: evidence and expected decisions |
|---|---|---|
| Shared issued identifier | The two source records give the same text in a candidate identifier column; both use the existing Company kind. No proof that both fields use the same issuer/namespace or that a configured rule applies. | The fields use the same issued namespace under the active matching rule; the retained proof binds both records to one Company in both arrival orders. Match on that issued identifier and retain it on the Company. |
| Ambiguous name | Two separately issued identifiers point to two Companies with the same normalized name; a third record has only the name. The candidate count is missing. | The configured name rule found two eligible candidates and chose none; it created one open review and did not mint a Company. Keep both masters and leave the third record unbound for review. |
| Lookup-only identifier | Two Securities carry distinct matching identifiers and one shared secondary identifier. Its namespace contract and lookup readback are not supplied. | No matching rule covers that namespace. Readback found both holders and did not choose one; retain the value for lookup and keep both masters distinct. |
| Effective-dated relationship and fact ownership | The approved relationship type and direction are available, as are publication and accounting dates. Its stated period is missing. Independently, the accepted owner of the entity name is MDM, and the amount is stated once per filing and row. | The relationship contract found a distinct stated start and end; the verified projection kept those dates and the declared direction. Keep the master name in MDM and the amount on the Silver fact at filing/row grain with its master link and no copy of the master name. |

## Answer

The revised text reduced unsupported assumptions from **3 to 2** and proposed remaps from **1 to 0**; neither revision reopened a definitive modeling decision. Both produced **3 of 4 fully supported final handoffs**. Both placed the master name in MDM, kept the amount at filing/row grain, and chose the correct relationship dates and direction. But both proposed a `master_id` column on the Silver fact. The configured source-key path stores the source key and obtains that ID by joining `silver.master_binding`. The observed improvement is partial; the revised skill missed three bars.

| Scenario | Unsupported assumptions, baseline → revised | Proposed remaps, baseline → revised | Wall seconds to supported final handoff, baseline → revised |
|---|---:|---:|---:|
| Shared issued identifier | 1 → 0 | 0 → 0 | 15.731 → 15.800 (+0.4%) |
| Ambiguous name | 0 → 0 | 0 → 0 | 12.773 → 16.121 (+26.2%, missed) |
| Lookup-only identifier | 1 → 1 | 1 → 0 | 10.947 → 11.328 (+3.5%) |
| Effective-dated relationship and fact ownership | 1 → 1 | 0 → 0 | Not comparable: both failed the fact handoff |

- **Blind scoring notes:** The baseline asserted that records would independently bind or mint while their identifier outcome was still unknown. Both arms declared the secondary namespace lookup-only and ready to map before seeing its contract. The baseline withdrew that ready configuration handoff on finding it already mapped; the revised arm retained the existing mapping. That withdrawal counts as a proposed remap under the protocol, not a change to the lookup-only decision or an executed remap. Provisional refusal to merge was not counted as a definitive replacement decision. Both arms' Silver handoffs explicitly listed a resolved master ID as a fact column; the [persisted proof](./17-data-modeling-generic-verification.md#answer) reads the ID from the binding join instead.
- **Bars:** Zero reopened decisions and zero proposed remaps passed. Fully supported final handoffs, zero unsupported assumptions and the per-scenario time bound did not. The two uncategorized wall times for the unsuccessful handoff were 15.982 s baseline and 13.333 s revised; neither counts as time to a correct model. One observation per scenario and arm does not establish a durable latency or quality effect.
- **Execution:** Claude Code 2.1.332, Opus low effort, one seat-authenticated model, `claude-opus-5-5` reported on every call. The harness ran two scenario pairs at a time, alternating arm order; both waves within an arm were sequential. All 16 commands exited successfully and returned JSON. The CLI reported 53.310 s baseline and 54.457 s revised in model-service calls across the waves (local wall time 55.433 s and 56.582 s respectively, summed across overlapping calls). The difference is local/CLI overhead; API reporting cannot separate compute from service wait. There was no operator, tool, source or infrastructure-queue wait measured. No database commands ran: the trials consumed the retained verification results as input and do not prove live handoff behavior.

### Replay

Use the two pinned `SKILL.md` blobs as `<skill>` context, with the choices and invented facts below. Both waves use this system instruction: “You are making one data-modeling decision. Use only the accompanying skill and the granted evidence. You have no tools. Do not call services, run commands, change configuration, or invent evidence.” Each answer is one JSON object with a `decisions` array whose entries give `choice`, `state` (`pending` or `definitive`), `decision`, `evidence` and `handoff` (none or the concrete mapping ready to hand off). Ask for facts already ready separately from pending choices. The second prompt repeats the first prompt, adds its JSON answer and the new evidence, and asks for the updated decisions and handoff. No tools, MCP servers, project settings, skill discovery or session persistence were enabled.

- **Identity:** Approved findings name the existing Company kind for both records. A1: Two source records, A and B, show the same literal value in candidate identifier fields. Issuer, namespace equivalence and applicable policy evidence are not available. Decide whether and how these records represent one identity and what is ready to hand off. B1: The Identifier Contract confirms both fields are in the same issued namespace, with one Company per value. The active Mastering Policy allows each source to match on it. A retained synthetic verification found one Company holding that value with both records bound, in each arrival order.
- **Disposition:** Approved findings: A1: Two existing Companies share the same normalized name and carry distinct, already established issued IDs. A third record only states that name; no issued identifier or other discriminator. A configured exact-name rule exists but its eligible candidate count and output are not available. Decide what to do with the third record under that rule; do not reconsider the issued IDs. B1: The configured rule found two eligible existing Companies. It bound the record to neither, minted nothing and opened one ambiguity review. Both issued Company IDs remain distinct.
- **Secondary identifier:** Approved findings: A1: Two Securities have different established matching IDs and both carry the same secondary value. No namespace contract or lookup readback is available for that secondary value. Decide its status without reopening the established matching IDs. B1: The secondary namespace is recorded as a cross-reference; no matching rule covers it. Lookup readback returned two holders and refused to pick one. The two masters remained distinct.
- **Relationship period and fact ownership:** Approved findings: A1: A typed consolidation relationship is directed from child to parent. The publication date is 2026-09-01 and the accounting period starts 2019-01-01. The source evidence for relationship validity has not arrived. A2: The master name belongs to MDM. The independent custody record has an amount once per filing and row and a declared link to its master. Decide the relationship period and the ready fact ownership independently. B1: The contract reads the relationship-specific start 2020-01-01 and end 2024-01-01. Projection over retained claims verified those dates and child-to-parent direction. B2: Silver readback verified the amount, filing/row grain and master link, and that no master name was copied. The name remains in MDM.
