# Compare vendor match, survivorship, and merge-reversal rules

Type: research
Status: resolved
Owner: Codex
Blocked by: none

## Question

What do Matrix IDM/Rimes, Informatica MDM, Ataccama ONE MDM, and Profisee
official sources establish about Source Record Binding, Identity
Consolidation, Field Survivorship, surviving IDs, and reversal? Which earlier
Clean MDM proposals should be revised before the policy interview?

## Comments

2026-09-17 — User requested vendor research and an interview using
`grill-with-docs`. Research is restricted to primary vendor sources, with
product/version boundaries and undocumented behavior stated explicitly.
Informatica and Ataccama/Profisee research were delegated to separate agents;
Codex is researching Matrix IDM/Rimes and integrating the results.

## Answer

Completed the [vendor comparison](../../../docs/research/clean-mdm-vendor-merge-rules-2026-09-17.md)
with separate [Informatica evidence](../../../docs/research/clean-mdm-informatica-merge-rules-2026-09-17.md)
and [Ataccama/Profisee evidence](../../../docs/research/clean-mdm-ataccama-profisee-merge-rules-2026-09-17.md).
Rimes public material does not establish detailed Matrix merge rules; Profisee
implementation documentation was login-gated. Product/version and access
limits are explicit in the reports. No vendor runtime was tested.

Research withdraws the unsupported numeric thresholds and universal
smallest-seed survivor recommendation, separates source binding from combining
established identities, and surfaces coherent fields, override expiry and
persistent split decisions. These are facts and revised recommendations, not
accepted Clean MDM policy. The human policy ticket remains unresolved.
