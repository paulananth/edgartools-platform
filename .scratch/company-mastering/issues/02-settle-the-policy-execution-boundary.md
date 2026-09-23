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

   **Amended 2026-09-23, when implemented.** ~~computed from that kind's
   block~~ — the digest covers the sections of the block that decide **which
   claim wins**, not the block whole. This decision's own build list puts
   classification, binding, bars and projection in that same block, and none of
   them change a field's winner. Digesting the block whole would move every
   field's recorded digest on a classification edit — the churn this decision
   exists to stop, reappearing inside one kind instead of between two.

   The sections are named in `survivorship.AUTHORITY_SECTIONS` and
   `NON_AUTHORITY_SECTIONS`, following the same written-down-not-inferred
   pattern as `store.PROTECTED_CONTRACT_PARTS`. A section in neither list is
   refused by name, so adding one is a decision somebody makes rather than a
   silent change to every field's recorded authority. `version` sits outside
   the digest because it already travels beside it. An absent or empty section
   is omitted rather than digested as empty, the way an absent mapping version
   and 1 are the same reading; a populated one is meant to move the digest.

   The one genuinely arguable member is `projection`: it changes what the
   entity exposes, but not which claim won. It is currently non-authority.

   **A profile field records its role's digest** (operator, 2026-09-23). A
   profile role is not an identity kind: `adviser` attaches to a company and a
   person, `fund` to a company and a fund structure
   (`evidence.PROFILE_KINDS`). Its rules therefore stay in one top-level
   `profile_fields` block rather than being written once per kind and left to
   drift apart, and its values record a digest computed from that role's own
   rules, with the role name carried alongside.

   Recording the enclosing kind's digest, which is what the first
   implementation did, made an edit to a role's rules invisible: it moved no
   recorded digest anywhere. That is the mirror image of the churn this
   decision exists to stop — over-coverage for a kind, no coverage at all for
   a role. An old body with no `kinds` block keeps recording the body digest
   here too, so the two halves of one policy never disagree about which era
   they are in.

   Considered and rejected: moving a role's rules under each kind
   (`kinds.company.profiles.adviser`). It buys per-kind divergence nothing has
   asked for and pays with the same rules written twice.
4. **Each kind keeps its own accepted bar** (Q4a): Company 99.9% precision at
   a one-sided 95% lower bound (Q11); Person 99% at 97.5% (its own ticket). A
   rule whose family has no bar cannot be activated. The bar gates fuzzy
   rules only: Q14 identifier binding activates by verifying an Identifier
   Contract, so tickets 04 and 05 do not wait on a precision study.
5. **Suspension lives in its own table** (Q5a, **amended 2026-09-22** — see
   below). The count survives batches and restarts; suspension is a state on
   that row with the evidence that caused it; the registered policy is never
   edited, so its digest stays valid. A suspended rule runs again only when a
   new policy version with a fresh verification is registered — never
   automatically.

   ~~keyed by the rule digest~~ and ~~the measured line stands for every
   automatic verdict~~ are **struck**. The row is keyed by
   `(policy_digest, kind, family, rule_id, rule_version)`. "Rule digest" names
   nothing in Clean MDM: a digest there is per *document*
   (`023_clean_mdm.sql:10-13`), and the spec's unit of rule identity is
   `rule.version` (`policy-language.md:428`).

   **The line is scoped where the spec puts it**: per `(kind, namespace)`
   Identifier Contract, counting distinct `(identifier, incoming normalized
   name)` **items**, and firing only on §9.3 deterministic verdicts.
   `warm_up_decisions: 10000, max_per_10k: 5` belongs to an Identifier
   Contract's tolerance block (`policy-language.md:269`), checked by §9.3,
   which covers a rule "whose `when` is identifier primitives only" and which
   therefore "has no precision to measure" (`:362-364`). A rule may name
   several namespaces, each with its own tolerance (`:367`), so one counter per
   rule would silently collapse distinct measured lines into one.

   Why it had to move: applied to every automatic verdict, the line demands
   99.95% at runtime from a rule accepted at 99.9%. A rule sitting exactly at
   its bar produces ten errors per ten thousand decisions; the chance of
   staying at or below five is about 7%, so it suspends itself permanently
   about nine times in ten. The two numbers cannot coexist under the general
   reading. They coexist under the spec's, because `max_per_10k` never counted
   decision errors.

   **What this leaves open, deliberately:** a rule accepted at 99.9% now has no
   runtime kill switch. That gap is real, and the honest answer is a measured
   line derived against that family's own bar — not `5/10k`, and not a number
   invented today. Recorded as fog on the map, to be decided once a Proving Run
   has produced rules to measure.
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
- a suspension table keyed by `(policy_digest, kind, family, rule_id,
  rule_version)`, and the runtime check that reads it before a **§9.3
  deterministic** verdict, counting per `(kind, namespace)`;
- group-aware selection in `survivorship.select_fields`.

### Acceptance tests these decisions owe

A Person-only edit leaves every Company value's recorded digest unchanged; a
group with an incomplete winner stays unknown and keeps its partial claims; a
deterministic rule crossing its namespace's line stops and stays stopped across
a batch boundary and a restart, while a measured rule at its own bar is never
stopped by that counter; a rule with no bar for its family cannot activate; a
Dataset Contract
naming a missing classification rule is refused.
