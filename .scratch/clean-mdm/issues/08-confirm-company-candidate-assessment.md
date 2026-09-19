# Confirm pre-application Company candidate assessment coverage

Type: grilling
Status: open
Owner: Codex
Blocked by: none

## Question

Should every proposed SEC/GLEIF source binding and consolidation of published
Company IDs retain a durable assessment before application, or only candidates
that are deferred or require review?

## Recommendation

Retain an assessment for every identity proposal, with immediate automatic
progression when qualified. Field-only refreshes retain their existing atomic
assertion/decision/effects history without a redundant staging gate. Keep
assessment persistence advisory in mdm_v2; revalidate evidence, qualification,
policy and affected identities inside the sole master transaction. Supersede
stale assessments and preserve rejected/superseded history.

## Evidence and prior decisions

- [Rebased Claude handoff review](../../../docs/specs/clean-mdm/design-reconciliation-2026-09-19.md)
  corrects the claims about preview and existing durable reviews.
- [Accepted Company Q1–Q12](../../../docs/specs/clean-mdm/company-policy.md)
  sets automatic processing, deferred outcomes and separate consolidation gates.
- This is Company interview Q13. Await the user's answer before implementing
  this assessment coverage rule. Other accepted decisions are not reopened.
