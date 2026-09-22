# Settle the Mastering Policy execution boundary

Type: grilling
Status: resolved 2026-09-22
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

## Answer

Operator decisions, 2026-09-22, one question at a time. Each names the code
it changes, so ticket 03 implements rather than re-decides.

1. **One home per identity kind** (Q1a). A kind's field rules move under
   `kinds.<kind>.fields`, beside its bars, lists, classification and binding.
   A policy body declares its shape; bodies already registered keep working
   unchanged and stay frozen, and any body using a new feature must use the
   new shape. Without this, a kind's version covers only half of that kind,
   which makes decision 3 impossible. Changes `survivorship.py:200` and the
   local Company policy's registration.
2. **Classification is governed, and the decided kind stays on the evidence**
   (Q2a). The Mastering Policy holds the classification rules; the Dataset
   Contract points at one by name and version; `adapters.py:58-68` still
   stamps the decided kind on the assertion, so an assertion id
   (`evidence.py:82-90`) never changes by itself. Pointing at a different rule
   version is a mapping change, so it produces a new mapping version and a
   second row under ticket 01, not a silent re-reading of old evidence.
   Registration must check that the named rule version exists.
3. **A field value records its kind's own digest** (Q3a), computed from that
   kind's block, with the authored kind version carried alongside for readers.
   The whole-body digest stays on the batch. A Person-only edit then changes
   no Company value, which is Codex's item 4. Changes `survivorship.py:274`
   and what `consumer.py:41` passes on.
4. **Each kind keeps its own accepted bar** (Q4a): Company 99.9% precision at
   a one-sided 95% lower bound (Q11); Person 99% at 97.5% (its own ticket). A
   rule whose family has no bar cannot be activated. The bar gates fuzzy
   rules only: Q14 identifier binding activates by verifying an Identifier
   Contract, so tickets 04 and 05 do not wait on a precision study.
5. **Suspension lives in its own table, keyed by the rule digest** (Q5a). The
   count survives batches and restarts; suspension is a state on that row with
   the evidence that caused it; the registered policy is never edited, so its
   digest stays valid. A suspended rule runs again only when a new policy
   version with a fresh verification is registered — never automatically. The
   measured line stands: `warm_up_decisions: 10000`, `max_per_10k: 5`.
6. **Coherent field groups are declared per kind** (Q6a). A group is filled
   whole from the highest-ranked source that can supply all of it; within one
   source the later publication wins; if no source is complete the group stays
   unknown rather than being stitched together, and the partial claims are
   kept as evidence. This closes the one case Q8 does not cover, and it is why
   an address can never be assembled from two sources.

### What ticket 03 must therefore build

- read field rules from `kinds.<kind>`, and refuse a new-shape body that also
  carries a top-level `fields` block;
- resolve the classification rule a Dataset Contract names, and refuse
  registration when it is absent;
- record the kind digest on each selected field, and keep the body digest on
  the batch;
- read the bar per `(kind, family)`, and refuse activation without one;
- a suspension table and the runtime check that reads it before any automatic
  verdict;
- group-aware selection in `survivorship.select_fields`.

### Acceptance tests these decisions owe

A Person-only edit leaves every Company value's recorded digest unchanged; a
group with an incomplete winner stays unknown and keeps its partial claims; a
rule crossing the line stops and stays stopped across a batch boundary and a
restart; a rule with no bar for its family cannot activate; a Dataset Contract
naming a missing classification rule is refused.
