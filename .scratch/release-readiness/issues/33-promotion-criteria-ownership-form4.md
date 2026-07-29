# 33 — Product-ready promotion criteria for Ownership / Form 4 (F6)

Type: grilling
Status: resolved
Blocked by: 27

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before
Ownership/Form 4 is promoted from Partial to Covered in the coverage matrix? Concrete platform
surface per the matrix footnote: gold `OWNERSHIP_ACTIVITY`, `OWNERSHIP_HOLDINGS`; silver
`sec_ownership_*`; MDM `IS_INSIDER`; Subject Bundle section `insiders`. Matrix note:
"Txn-level Form 3/4/5 + graph edge; ER skill 'insider narrative' contract = ERDP-05."

Note (2026-07-26 release-readiness ticket 24, resolved): `IS_INSIDER` full-universe GO
verification already exists as a separate, distinct concern (doctrine + state machine + 10-CIK
verify 146/146) — this ticket's promotion checklist is about the ER-skill-facing product
contract (does an insider narrative read path exist with the right fields/grain/freshness for
skills that need it), not a restatement of ticket 24's MDM relationship-completeness gate.
Keep the two clearly separated in the answer.

Write this as a numbered list of criteria (coverage breadth, transaction-level completeness,
graph-edge (`IS_INSIDER`) agreement with ownership rows, Bundle `insiders` section field
completeness), each with a concrete, checkable acceptance query or procedure, following the
exact method and rigor of `erdp-coverage-promotion` tickets 03–06 — grounded in real
schema/code, cross-checked against ticket 27's ER-skill survey findings for this product,
adversarially stress-tested for what a naive checklist would miss.

## Answer

Grounded in the real schema (`EDGARTOOLS_GOLD.OWNERSHIP_ACTIVITY`/`OWNERSHIP_HOLDINGS`, MDM
`IS_INSIDER` graph edges — all live-checked 2026-07-29) and ticket 27's F6 survey findings.
Unlike F1-F3, this product **does** have a documented Subject Bundle section already
(`docs/subject-bundle-read.md`'s `insiders` row: "Graph `IS_INSIDER` **and** gold ownership
source accession") — so criterion 1 here is about whether the existing contract is met, not
whether a contract exists at all.

1. **Real, serious coverage gap — found live, not anticipated by the ticket's own framing.**
   `OWNERSHIP_ACTIVITY` has 7,035 rows across only **32 distinct companies**;
   `OWNERSHIP_HOLDINGS` has 2,100 rows, also only 32 companies. Against a ~30,000-company tracked
   universe, this is pilot-scale, not production-scale — similar in character (though smaller in
   blast radius, and NOT spun into its own root-cause ticket since it's scoped to this one
   product) to ticket 41's fundamentals finding. **This is the actual promotion blocker**, not a
   documentation gap: idea-generation's stated need (insider buying/selling, insider ownership %,
   cross-sectional across a screening universe — ticket 27 F6) cannot be met when 99.9% of
   tracked companies have zero ownership rows.
   Acceptance (currently failing): `SELECT COUNT(DISTINCT company_key) FROM OWNERSHIP_ACTIVITY`
   should be within an order of magnitude of the operating/issuer-eligible universe (~2,462 per
   ticket 40's entity_type breakdown), not 32.

2. **`IS_INSIDER` graph-edge agreement with ownership rows.** Live-checked the active graph
   generation (`ticket20-strict-endpoint-seal-850ea34-20260725T130457Z`): 2,608 `IS_INSIDER`
   edges exist. Given ticket 24 (Insider-scoped EMPLOYED_BY completeness, resolved) already
   verified `IS_INSIDER` doctrine/derivation correctness on a 10-CIK sample (146/146) as a
   **separate MDM relationship-completeness concern** — this criterion is narrower: every
   `IS_INSIDER` edge should have a corresponding `OWNERSHIP_ACTIVITY` accession it derives from,
   not a restatement of ticket 24's own gate.
   Acceptance: `SELECT COUNT(*) FROM <IS_INSIDER edges> e LEFT JOIN OWNERSHIP_ACTIVITY oa ON
   oa.accession_number = e.source_accession WHERE oa.accession_number IS NULL` = 0.

3. **Transaction-level completeness for covered companies.** For the (currently only 32)
   companies with any ownership data, transaction code / shares / price / derivative flag should
   be non-null for the fields idea-generation actually reads (buy/sell direction, recency,
   ownership %) — a data-quality check scoped to what exists today, separate from criterion 1's
   coverage-breadth gate.

4. **90-day recency window, per idea-generation's stated bar.** The only skill-stated freshness
   requirement (ticket 27 F6): "Insider buying in last 90 days." A promoted product must
   guarantee transactions filed within the last 90 days are present within a bounded lag (e.g.
   filing-to-load lag ≤ 5 business days) — not same-day, but not a stale multi-month backlog
   either.

5. **Bundle `insiders` section coverage-flag correctness.** Per the existing contract
   (present/empty/unavailable), a CIK with zero ownership rows must resolve to `empty`, not
   silently omitted or misreported as `unavailable` (which per the Bundle's own semantics means
   "platform could not assert completeness," a different claim than "genuinely zero insiders").

**Explicitly not required for promotion:** insider ownership % as a point-in-time snapshot
history (initiating-coverage's need is single-snapshot, explicitly "if disclosed" — soft, not
hard); a full multi-year transaction history sweep (idea-generation's need is a rolling 90-day
window, not history depth); morning-note/earnings-analysis/thesis-tracker-specific criteria —
confirmed via ticket 27's survey that none of these three states any textual need for this
product at all.

**Known residual risk:** criterion 1 (coverage) is the real, hard blocker — 32 companies is not
a scope decision, it looks like ownership data has only ever been loaded for a small pilot set,
same shape as F4's fundamentals gap but not investigated to the same root-cause depth here (out
of scope for this ticket; worth its own look if this map continues past the F1-F12 pass).
