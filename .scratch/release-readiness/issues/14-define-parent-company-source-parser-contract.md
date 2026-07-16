# Define Parent-Company Source and Parser Contract

- Type: research
- Status: resolved
- Blocked by: none
- Blocks: 22

## Question

What Exhibit 21 source inventory, parser behavior, normalization rules, and evidence contract will prove complete `HAS_PARENT_COMPANY` derivation at the Release Data Watermark?

## Exit criteria

- Define the complete Exhibit 21 candidate inventory.
- Define success, not-applicable, ambiguity, quarantine, and retry outcomes.
- Define canonical entity resolution and provenance requirements.
- Bind derivation to applicability and per-type parity evidence.
- Assign implementation and release-acceptance owners.

## Resolution

Approved SEC annual-filing attachment indexes plus Exhibit 21 for domestic filers and Exhibit 8 for Form 20-F filers. The relationship is deliberately scoped as a disclosed subsidiary pointing to the filing registrant, not an inferred immediate legal-parent hierarchy. The contract defines full candidate inventory, deterministic parsing, non-CIK company identity, temporal semantics, terminal outcomes, and exact MDM/graph parity.

Decision artifact: [`docs/release-readiness/parent-company-source-parser-contract.md`](../../../docs/release-readiness/parent-company-source-parser-contract.md)

Implementation remains required under ticket 22; resolving this research ticket does not make `HAS_PARENT_COMPANY` launch-ready.
