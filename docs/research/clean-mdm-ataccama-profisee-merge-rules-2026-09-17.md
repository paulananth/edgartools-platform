# Clean MDM: Ataccama and Profisee merge rules

Researched 2026-09-17. Status: research and design recommendations, not accepted policy or implementation evidence. Terminology follows [CONTEXT.md](../../CONTEXT.md); proposed policy is [Shared Merge Stage](../specs/clean-mdm/merge-stage.md).

## Evidence scope

Ataccama provides public implementation documentation. Its `latest` documentation identified itself as ONE MDM 17.1.0 during this research. The identity-stability findings below are also verified against the fixed 17.0.0 URL. Several other fixed-version URLs failed to load; those claims explicitly use the dated `latest` snapshot rather than claiming a fixed-version verification.

Profisee's public pages describe capabilities. The official technical-documentation and 2026R1 release-note links both redirected to login. This research therefore does not establish Profisee's detailed operational semantics. [Technical documentation](https://support.profisee.com/wikis/profiseeplatform/before_you_begin), [2026R1 release notes](https://support.profisee.com/wikis/release_notes/New_Features_and_Enhancements_for_2026-R1).

## Ataccama findings

| Decision area | Documented behavior | Implication for Clean MDM — inference |
| --- | --- | --- |
| Attach source evidence versus combine identities | Automatic matching does not combine two established identities. When incoming evidence bridges existing groups, it joins the best group and generates proposals for the others. Existing identities survive changes to underlying values. An explicit merge retains one existing master ID. [17.0.0 Matching Architecture](https://docs.ataccama.com/mdm/17.0.0/matching/matching-architecture.html) | Decide these operations separately. An exact identifier match can authorize attachment without authorizing consolidation of two published Company Identities. |
| Candidate selection and incompatible kinds | Partitions prevent cross-kind comparison. Exact key rules create candidate groups; detailed rules can use exact or approximate comparisons. [Matching step, latest](https://docs.ataccama.com/mdm/latest/matching/matching-step-behind-the-scenes.html) | Company Identity and Person Identity separation belongs before scoring. Blocking keys are not necessarily sufficient identity evidence. |
| Conflict exclusion | Constraints apply across the resulting group: different non-null constraint values cannot coexist. Null can match a known value. Constraint changes can force a split and generate review proposals. [Matching step, latest](https://docs.ataccama.com/mdm/latest/matching/matching-step-behind-the-scenes.html) | Preserve the draft's whole-component identifier veto; test the bridge case where missing identifiers connect incompatible known identifiers. |
| Scores and review | Matching rules create groups; proposal rules request review. Proposal confidence prioritizes review and does not decide automatic grouping. Keeper selection is configurable. [Matching step, latest](https://docs.ataccama.com/mdm/latest/matching/matching-step-behind-the-scenes.html) | No justification here for universal 0.85 Company or 0.80 Person thresholds. Calibrate candidate recall and reviewer capacity separately from automatic-match precision. |
| Field selection | Matching and merging are separate phases. Merge rules can select blocks containing one or several attributes. Source, cleansed, matching, and master layers remain distinct. [MDM Model, latest](https://docs.ataccama.com/mdm/latest/product-overview/mdm-model.html) | Permit coherent field groups, such as a complete address. Independent street/city/postcode winners can produce an address no source asserted. |
| Steward overrides | Configuration distinguishes permanent overrides from temporary ones. Temporary overrides can expire when incoming data equals the override, when the original source value changes, or when an expression matches. [Model configuration, latest](https://docs.ataccama.com/mdm/latest/configuration/model.html) | Set override lifecycle by field or field group. Decide whether a new source correction ends an override; precedence alone is incomplete. |
| Split and survivor choice | Stewards can select a surviving master ID, detach instances into a new master, or move them to another master. Related master records are reprocessed during consolidated merges. An authored record must survive a merge with a consolidated record. [Merging and Splitting Records, latest](https://docs.ataccama.com/mdm/latest/editing-master-data/merging-and-splitting-records.html) | Distinguish investigation, source reassignment, and consumer correction. Do not promise restoration of an old ID merely because splitting is available. |
| Persist manual decisions | Rematch preserves manual matches and splits by default; a separate strategy removes them. Whole-master rematch is recommended for consistency. [Merging and Splitting Records, latest](https://docs.ataccama.com/mdm/latest/editing-master-data/merging-and-splitting-records.html) | Record a durable negative match decision after an incorrect merge. Otherwise replay can recreate the same bad merge. |
| Later updates and retirement | Changes to configured business attributes can create proposals without changing the current master ID; this route creates merge proposals, not split proposals. Inactive instances normally remain matchable but can be excluded from field selection. A configured deletion strategy can instead remove them. [Working with Matching, latest](https://docs.ataccama.com/mdm/latest/matching/working-with-matching.html) | Keep identity continuity, field eligibility, and source-retirement evidence separate. Specify how corrected identifiers trigger investigation without silently moving source bindings. |

The reviewed Ataccama documents do not establish a universal null/authorized-clear/retraction contract equivalent to our proposal, a stable-alias API for every retired ID, or a complete procedure for allocating later manual corrections after a split. These remain our explicit design obligations.

## Profisee findings and limits

Profisee publicly distinguishes matching, logical merging, and field survivorship. It advertises deterministic and probabilistic matching, review of uncertain matches, steward-selected field winners, audit trails, and automated selection by completeness, recency, source trust, or custom rules. These are product capability claims, not a verified precedence algorithm. [Matching and survivorship](https://profisee.com/solutions/initiatives/matching-and-survivorship/).

The dated 2026R1 announcement says AI Vector matching uses a selected embedding model and configured thresholds, combined with other similarity methods. It does not establish a universal identity confidence threshold or justify fuzzy automatic matching for SEC entities. This research does not infer that 2026R1 is the newest release. [2026R1 announcement, March 25, 2026](https://profisee.com/blog/profisee-announces-new-release-2026-r1/).

Profisee's general MDM guide explains why retained history is needed to undo a mistaken merge and recommends evaluating false matches versus missed matches. This is useful design guidance, not proof of a particular product unmerge API. [MDM guide, updated August 2, 2024](https://profisee.com/master-data-management-what-why-how-who/).

Not verified from accessible Profisee implementation docs: group-wide identifier exclusions, established-identity merge protection, surviving-ID order, aliases, null/clear/retraction semantics, correlated-field selection, persistence of negative matches, unmerge restrictions, or treatment of post-merge updates.

## Proposed interview order

These questions reopen recommendations; none are accepted decisions.

1. **Automatic authority:** May the Merge Stage attach new source evidence automatically while requiring review before it combines two established identities? Recommendation: yes. Record disputed bridges without choosing a different identity merely from a similarity score.
2. **ID stability:** Must a published Company Identity keep its ID when a new source anchor sorts before its original anchor? Recommendation: yes. Replace the draft's minimum-seed canonical-ID rule with explicit surviving-ID decisions. Rebuild determinism then includes the retained decision and binding history as inputs.
3. **Field groups:** Must all parts of an address come from one accepted assertion unless a separate normalization rule explains the transformation? Recommendation: yes; define field groups and their provenance.
4. **Override expiry:** Does a source correction cancel an override or create a review task? Recommendation: define this by field policy; preserve the override until explicit expiry or review for disputed legal facts.
5. **Correction memory:** After a split, must a negative match decision block automatic reunion until a steward revokes it? Recommendation: yes, with explicit scope so unrelated future identities are not blocked.

Vendor behavior is comparative evidence. The Clean MDM Change Journal, atomic publication intent, recovery procedure, and acceptance gates still need repository-specific implementation and tests.
