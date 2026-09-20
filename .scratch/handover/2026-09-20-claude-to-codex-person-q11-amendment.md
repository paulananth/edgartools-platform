# Handover — 2026-09-20, Claude → Codex (Clean MDM): Person Q11 amendment

## TL;DR

The operator asks you to amend accepted Q11 **for the Person kind only**:
allow the Tier B compound-context-key rule (same issuer/firm CIK + exact
normalized name + consistent role) to auto-bind at **≥ 99%** measured
precision instead of 99.9%. Your method, your adversarial cases, your
zero-hard-veto rule — one number, one kind, one rule family.

Read: [`.scratch/clean-mdm-person-q11-amendment-proposal/issues/01-write-person-q11-amendment-proposal.md`](../clean-mdm-person-q11-amendment-proposal/issues/01-write-person-q11-amendment-proposal.md).

## Context you don't have yet

The [Person Consumer Contract](../person-consumer-contract/map.md) map is
being worked in parallel with your Company gate, the same way the Company
contract was — Claude plans, you build after the gate, nothing collides.
Four code traces (research 11–14) and two primary-source studies (15, 16)
are on `main`. The ones that touch you:

- **`OwnerID` in ADV `IA_Schedule_A_B` is a CRD-system individual record id**
  — present on 99.6% of individual rows, stable across monthly archives,
  disjoint from firm CRDs, not unique per natural person (issuer-admitted
  duplicates). The archive your `adv_bulk_ingest.py:126` already downloads
  contains it, unread. The Person contract puts reading it in scope.
- **The DEF 14A name defect is upstream in edgartools** (`html_extractor.py:857-864`),
  not the platform — relevant if your Person integration ever consumes
  `sec_executive_record`.
- Legacy Person matching's "issuer context" is inoperative (`match.py:123-132`);
  don't inherit its bands.

## The operator's principle, verbatim

"mdm must have one id for one person, these ids must be cross reference
ids never unique id, mdm must create a unique id to reference both, we
cannot create duplicate records that defeats the purpose of mdm."

That is your `identity.entity_id` + bound identifiers model exactly; the
contract is written to it.

## Still pending from you

- Pre-merge candidate table (2026-09-19) — now load-bearing for Tier C.
- Per-family checkpoint key (2026-09-19).
- The continuity-proof home question (`mdm_v2.dataset.body`?) from the
  shared-foundation handover.

## One thing the operator must do

Point your next session here; your map's "Start here" won't surface it.
