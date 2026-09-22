# Settle the Mastering Policy execution boundary

Type: grilling
Status: open
Blocked by: 01

## Question

The policy language is written and proposed; Codex parked six items before any
runtime executes it. Settle each, and amend the spec:

1. **One canonical field layout.** The spec shows both `kinds.<kind>.fields`
   and the existing top-level `fields`. Pick one, and say how a body written
   the other way is treated.
2. **Where classification sits** in the body, and how it reaches `normalize`.
3. **Per-kind versions against one body digest.** A Person-only edit must not
   churn every Company business hash. Depends on ticket 01's answer.
4. **Confidence bar.** The prototype uses a one-sided 97.5% bound; accepted
   Company text says 95%. Declare which, and what coverage each claim needs.
5. **Rule suspension at runtime.** A durable, replayable counter or
   suspension contract that does not mutate the registered policy and does not
   vanish at a batch boundary.
6. **Survivorship.** Coherent field groups and publication-time ordering, with
   the acceptance tests that show them working.

## Inputs

[Policy language](../../../docs/specs/mdm/policy-language.md),
[Codex's reconciliation list](../../handover/2026-09-20-codex-policy-language-reconciliation.md),
[Company policy](../../../docs/specs/clean-mdm/company-policy.md).
