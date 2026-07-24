# 02 — Parser Rewrite Target Format and Private-Fund-Detail Strategy

Type: grilling
Status: open
Blocked by: 01
Blocks: 04, 05, 06

## Constraint (non-negotiable, restated by the user 2026-07-24)

ADV data must reach the Neo4j/Snowflake graph end to end. Whatever this
ticket decides for private-fund detail, it must not become a reason to skip
Adviser/Fund entity resolution or graph sync altogether — only
`MANAGES_FUND` edge fidelity is allowed to degrade if bulk data truly lacks
per-fund PFID identity. See map.md Notes for the full statement.

## Question

Given ticket 01's findings on what SEC actually publishes in bulk today,
decide:

1. What format does `adv_bulk_ingest.py` get rewritten to parse — the Firm
   Roster CSV directly (single file, ~150 columns), a rediscovered
   relational source (if ticket 01 finds one still exists), or both (a
   format-detecting dual path)?
2. What is the private-fund-detail strategy? Candidates from last session's
   blocker doc: (a) store only aggregate counts and redefine what
   `sec_adv_private_fund` / the `MANAGES_FUND` relationship represents under
   the new constraint; (b) use a rediscovered real per-fund bulk source if
   ticket 01 finds one; (c) mark private-fund detail unavailable at bulk
   scale and rely solely on `parse-adv-bronze`'s EDGAR-native-filed ADV path
   (which only covers advisers that also happen to be public EDGAR filers —
   a small subset).
3. Does the answer to (2) require revising `adviser-fund-source-contract.md`
   (specifically the "no name-only identity," PFID-required-for-every-edge
   language), and if so, what does the revised contract say?
4. What happens to firm-identity, office, and disclosure-event data
   (`sec_adv_filing`, `sec_adv_office`, `sec_adv_disclosure_event`) — do
   these map cleanly from Firm Roster columns as the blocker doc guessed, or
   does inspection reveal gaps there too?

## Answer

(pending)
