# 34 — Product-ready promotion criteria for 13F / holders (F7)

Type: grilling
Status: resolved
Blocked by: 27

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before
13F/holders is promoted from Partial to Covered in the coverage matrix? Concrete platform
surface per the matrix footnote: gold `SEC_THIRTEENF_HOLDING`; MDM `INSTITUTIONAL_HOLDS`;
Subject Bundle `holders_of_subject`, `subject_as_manager_portfolio`. Matrix note: "Holdings
period + lag rules exist on Bundle; no ER 'holder pack' acceptance yet."

Note (2026-07-26/27, `sharded_reader.py` fix + INSTITUTIONAL_HOLDS reclassification): this
product's underlying MDM relationship (`INSTITUTIONAL_HOLDS`) was, as of this map's ticket 06,
reclassified from non-blocking to a **required** relationship type for release GO — read
ticket 06 (`.scratch/release-readiness/issues/06-define-full-chain-launch-gate.md`) and the
"INSTITUTIONAL_HOLDS / EMPLOYED_BY 5-whys" entry in CLAUDE.md before writing this checklist, so
the ER-skill-facing promotion criteria here don't duplicate or contradict the separate
GO-gate parity requirement.

Write this as a numbered list of criteria (coverage breadth, 13F filing-lag correctness, holder
pack completeness for both directions — subject-as-held and subject-as-manager, Bundle field
accuracy), each with a concrete, checkable acceptance query or procedure, following the exact
method and rigor of `erdp-coverage-promotion` tickets 03–06 — grounded in real schema/code,
cross-checked against ticket 27's ER-skill survey findings for this product, adversarially
stress-tested for what a naive checklist would miss.

## Answer

Grounded in live schema (`EDGARTOOLS_GOLD.SEC_THIRTEENF_HOLDING`/`INSTITUTIONAL_HOLDINGS`, the
graph mirror) and ticket 27's F7 survey findings — the weakest-grounded of all 12 products from
an ER-skill-text perspective (no skill states a field-level need; idea-generation's "check
ownership data... avoid crowded trades" is a qualitative gut-check, not a data-consumption
request; initiating-coverage's "major shareholders" bullet is generic and explicitly optional).
Given that, this checklist is built from the **platform's own committed contract**
(`holders_of_subject`/`subject_as_manager_portfolio` are already named, documented Bundle
sections) rather than a specific skill demand — the Bundle promises this data exists, so if it's
going to be promoted at all, it needs to actually be correct and complete, independent of how
thinly any one skill asks for it today.

1. **Underlying data is genuinely healthy — not the blocker here.** Live-verified:
   `INSTITUTIONAL_HOLDINGS` has 6,799,919 rows, 41,225 distinct CUSIPs, populated via a real bulk
   load (per ticket 41's cross-check). This is the one F1-F12 product this session found with
   the least data-health risk.

2. **A real gap found live: the currently-active MDM/graph generation has no relationship type
   literally named `INSTITUTIONAL_HOLDS`.** Checked the active graph generation
   (`ticket20-strict-endpoint-seal-850ea34-20260725T130457Z`, and the newer, still-unactivated
   `residual-full-20260726T010010Z`) directly: both contain only `MANAGES_FUND`, `EMPLOYED_BY`,
   `HOLDS`, `COMPANY_HOLDS`, `IS_INSIDER` as relationship types — **no edge type named
   `INSTITUTIONAL_HOLDS` exists in either generation**. Whether `HOLDS`/`COMPANY_HOLDS` are the
   actual on-the-ground name for what CLAUDE.md and this map's tickets 04/06/24 call
   `INSTITUTIONAL_HOLDS`, or whether that relationship type has never actually been synced to
   the graph despite the underlying holdings data being real and complete, was **not resolved by
   this ticket** — this is a naming/sync question for whoever owns the graph-sync code
   (`edgar_warehouse/mdm/snowflake_graph.py`) to confirm, not assumed here either way.
   Acceptance (cannot be verified until the naming question above is resolved): the ER-facing
   `holders_of_subject`/`subject_as_manager_portfolio` sections' graph-backed portion must
   resolve to a real, named relationship type in the active generation — not silently return
   `empty` for every subject because the type name doesn't match what the read code queries for.

3. **Do not restate ticket 06's strict-inheritance gate.** Ticket 06 (Full-Chain Launch Gate)
   already made `INSTITUTIONAL_HOLDS` parity a required, no-exclusion-valve relationship type for
   release GO. This ticket's criteria are about the ER-facing *read* contract (does an agent
   asking for `holders_of_subject` get correct, complete data), not a duplicate of that
   MDM-completeness gate — kept explicitly separate per this ticket's own framing.

4. **Bidirectional holder-pack completeness.** Per the Bundle's two named sections: for a
   subject CIK, `holders_of_subject` (institutions holding this issuer) and, separately,
   `subject_as_manager_portfolio` (this CIK's own 13F book, if it's itself a manager) must both
   resolve correctly and independently — a CIK that is purely an issuer should show `empty` (not
   `unavailable`) for the manager-portfolio section, and vice versa.

5. **Latest Complete Holdings Period + lag, per the Bundle's own documented rule.**
   `docs/subject-bundle-read.md`'s `holders_of_subject` row cites "Latest Complete Holdings
   Period + lag" (also defined in `CONTEXT.md`'s "Latest Complete Holdings Period" glossary
   entry) — the promoted product must expose the reporting period and known lag explicitly, not
   just the raw holdings rows, per that glossary term's own `_Avoid_` list ("treating missing
   13F as zero position without unavailable").

6. **Join integrity — CUSIP-to-issuer resolution.** Per this session's earlier CUSIP cross-check
   (ticket 40's addendum): CUSIP→issuer-name matching is imperfect (subsidiary/parent
   conflation, e.g. Charter Communications Holdings LLC matching its parent CHTR's CUSIP). A
   promoted `holders_of_subject` section must resolve CUSIP→issuer via a real identity join (CIK
   or MDM `MDM_SECURITY.issuer_entity_id`), not name-matching — flagging this as a real
   implementation risk given `MDM_SECURITY.cusip` was found unpopulated (0 of 97 rows) in that
   same investigation.

**Explicitly not required for promotion:** a computed "crowded trade" score or analyst-coverage
count (idea-generation's own stated language is qualitative, not a request for a platform
metric); any field-level holder-list detail beyond what the two named Bundle sections already
commit to (no skill asks for more).

**Known residual risk:** criterion 2 (the relationship-type-naming question) is a real open
question this ticket surfaces but does not resolve — treat this as a concrete follow-up for
whoever next touches `snowflake_graph.py`'s relationship-type mapping, not a settled fact either
way.
