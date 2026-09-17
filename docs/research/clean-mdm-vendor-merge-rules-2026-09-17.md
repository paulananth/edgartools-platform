# Clean MDM: vendor comparison and revised decision questions

Date: 2026-09-17. Status: research and recommendations; no new policy accepted.
Research used `grill-with-docs`, `grilling`, `domain-modeling`, and `research`.
No vendor system was run. Public documentation depth differs substantially.

## What changed in the proposal

The earlier exact-only automatic policy and numeric 0.85/0.80 review thresholds
were our proposals, not established MDM practice. The numeric values are
withdrawn pending a labeled corpus. The blanket smallest-seed surviving-ID
recommendation is also withdrawn. Published identity stability needs its own
rule, separate from deterministic processing of source evidence.

Our Merge Stage still owns identity and fields. The
[glossary](../../CONTEXT.md) now distinguishes Source Record Binding,
Identity Consolidation, and Field Survivorship so one word, “merge,” does not
hide three different decisions. Company/Person separation, governed profiles,
authoritative-identifier conflict protection, and atomic journal/publication
requirements remain the accepted direction.

## Comparison

| Product / evidence | Matching and identity | Field selection | Reversal and limits |
| --- | --- | --- | --- |
| Matrix IDM / Rimes public material | Rimes describes investment-data mastering and Matrix investment intelligence; no implementation-level identity merge rules were found | Public descriptions cover mastered data and lineage; exact winner/null order not verified | Survivor-ID, split/unmerge, negative-match and transaction semantics not verified. [Matrix fact sheets](https://www.rimes.com/rimes-fact-sheets-investops-europe-paris/), [Rimes data management](https://www.rimes.com/solutions/data-management/) |
| Informatica Multidomain MDM, explicitly versioned 10.x guides | Match results can precede Merge/Link. Established consolidated IDs beat new records in the documented 10.4 batch case; explicit Merge targets survive | Column-level trust can account for source, quality and age; null behavior is configurable | Linear/tree unmerge differ; child cascade is separate. Older Hub rules are not automatically SaaS rules. [Detailed evidence](clean-mdm-informatica-merge-rules-2026-09-17.md), [survivor rule](https://docs.informatica.com/master-data-management/multidomain-mdm/10-4/configuration-guide/part-4--configuring-the-data-flow/mdm-hub-processes/about-informatica-mdm-hub-processes/rowid_object-survivorship.html), [trust](https://docs.informatica.com/master-data-management/multidomain-mdm/10-5-hotfix-4/configuration-guide/part-4--configuring-the-data-flow/mdm-hub-processes/load-process/trust-settings-and-validation-rules/trust-settings.html) |
| Ataccama ONE MDM 17.0.0 and dated latest/17.1.0 pages | Rules can use approximate comparison; automatic matching protects two existing identity groups from consolidation | Rules can choose a block of related attributes; override expiry is configurable | Split/rematch behavior preserves manual decisions by default; detailed post-split correction ownership still needs our contract. [Detailed evidence](clean-mdm-ataccama-profisee-merge-rules-2026-09-17.md), [architecture](https://docs.ataccama.com/mdm/17.0.0/matching/matching-architecture.html), [model](https://docs.ataccama.com/mdm/latest/product-overview/mdm-model.html) |
| Profisee public product material | Advertises deterministic/probabilistic matching and steward review | Advertises source trust, recency, completeness and custom rules | Technical documentation redirected to login; detailed survivor/null/unmerge rules remain unverified. [Public capabilities](https://profisee.com/solutions/initiatives/matching-and-survivorship/), [technical docs](https://support.profisee.com/wikis/profiseeplatform/before_you_begin) |

These are comparisons of documented behavior, not a product ranking or a
recommendation to buy a platform. Missing public evidence does not establish
that a product lacks a capability.

## Matrix IDM / Rimes findings

Rimes' own 2022 account describes integration of Matrix into its offering and
identifies Matrix IDM with asset-allocation/rebalancing capabilities.
[Rimes update, July 18, 2022](https://www.rimes.com/rimes-a-year-of-change-and-growth/).
Its fact sheets identify Matrix as its investment intelligence platform.
This supports interpreting the user's product name as Matrix IDM/Rimes; it
does not make all Rimes data-management features a verified Matrix engine rule.
[Matrix fact sheets](https://www.rimes.com/rimes-fact-sheets-investops-europe-paris/).

The public data-management page describes validation, enrichment, lineage and
harmonized security/entity masters. It does not disclose match scoring,
identifier conflict vetoes, null handling, survivor selection, or unmerge
mechanics. Searches of Rimes/Matrix public pages for these rules did not yield
an implementation manual. Those cells stay unknown rather than borrowing
rules from a different product. [Data management](https://www.rimes.com/solutions/data-management/).

## Proposed policy changes and tradeoffs

1. **Separate automatic binding from consolidation.** A validated rule can
   attach a new source record to one established identity. Combining two
   already accepted/published identities requires a steward decision in the
   proposed first release. Unlike Ataccama's documented best-group attachment,
   our recommendation sends a bridge between multiple eligible groups to
   review without selecting a group. This stricter behavior is our choice.
2. **Use evidence to set match rules.** Exact IDs and scored multi-attribute
   rules are eligible mechanisms, but every rule needs entity-specific tests
   and a measured false-match limit before automatic activation. An exact
   shared ID does not bypass contradictory authoritative IDs, kind checks,
   temporal scope or uniqueness. Candidate recall needs separate measurement.
3. **Preserve published IDs.** New source evidence must not rename an accepted
   identity. An approved consolidation explicitly selects an existing survivor
   and retains the losing ID as a versioned alias. A rebuild that must reproduce
   exact public IDs restores the binding/decision/ID registry as part of its
   input. Regenerating IDs from only the latest source set is a different
   requirement; it must not silently replace registry-preserving replay.
4. **Select coherent facts.** Preserve type-plus-field authority, with declared
   groups for facts such as address components. Apply quality/validity and any
   declared freshness rule at a pinned as-of time before source priority. Use
   recency within the eligible authority order. Do not average conflicting
   legal facts or create an address that no source asserted.
5. **Keep missing/clear/retract distinct.** A blank does not silently erase a
   known value. A clear is a separately authorized claim; withdrawal of a
   source contribution permits recomputation from remaining eligible evidence.
6. **Give overrides a lifecycle.** A steward correction persists until its
   specified expiry or explicit revocation. A contradictory source update
   opens review. Fields may declare a different expiry policy only explicitly.
7. **Prevent repeated bad merges.** After an incorrect merge, preserve a
   scoped Match Exclusion until an evidence-bound decision revokes it. Restore
   source bindings and recompute fields/relationships, retaining later valid
   corrections; facts with uncertain ownership require review. This is our
   recovery contract, not a claim that all vendors implement it identically.

The ID recommendation trades source-set-only UUID regeneration for public
identity continuity. Steward review trades some throughput for control over
changes that affect already published consumers. The user must choose these
tradeoffs; vendor documentation cannot approve them on the user's behalf.

## Interview frontier

The active questions and answers live only in the
[Wayfinder policy ticket](../../.scratch/clean-mdm/issues/01-set-merge-stage-policy.md).
That ticket remains claimed and unresolved. Numeric thresholds, override
durations, and the detailed survivor rule are later decisions that depend on
the first-round authority and identity-stability choices.

After the user answers, record accepted terms in the glossary and capture
hard-to-reverse, non-obvious tradeoffs in a concise ADR. No accepted ADR is
created from research alone. Domain representations outside the already
accepted Company/Person/profile direction remain a separate unresolved part
of the original gate; this merge-focused research does not decide them.
