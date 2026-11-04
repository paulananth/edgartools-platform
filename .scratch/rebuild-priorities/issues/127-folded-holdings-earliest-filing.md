# 127: A folded holding's earlier filing and other issuer count on its Security

Priority: 127. Map: [Rebuild priorities](../map.md). Found by ticket 120's
Spec review (2026-10-20).

Type: task. Status: open. Blocked by: none.

## What is open

Ticket 120 folds an ISIN-only holding into the CUSIP's Security when FIGI
attaches its ISIN to that CUSIP one to one. `fold.yaml` keys the folded
holdings' filed facts by the CUSIP, and `record.yaml` takes them only where
the CUSIP's own holdings state none. Two rulings are therefore not yet whole
for a folded Security:

- Ticket 113's "earliest filing date of the holdings that name its issuer":
  a folded holding filed earlier does not move the ISSUED_BY start back.
- One issuer LEI over all the Security's holdings: CUSIP holdings with LEI A
  and folded holdings with LEI B give A, where counted together they give no
  link.

The source engine has no expression that takes the earlier of two dates or
merges two member counts, so this needs an engine primitive (or the reduce
to count the folded holdings by CUSIP, which it cannot before FIGI attaches).

## Checklist

- [x] Count (2026-11-04 07:36 ET): measured on the 2026 Q2 file with a fold by FIGI, 5,381 Securities received a folded holding; 2,688 had a folded holding filed earlier and 99 a different issuer LEI. Correction in the same entry: ticket 138 ended that fold, so these counts describe code that no longer runs and the primitive they argued for is not needed (next line)
- [x] Choose (2026-11-04 07:36 ET): the operator chose the engine primitive on the stale counts above. Measured afterwards on today's code (`tests/integration/test_nport_one_security_two_records.py`, 2 tests pass): an ISIN-only holding and a CUSIP holding of one Security are two records MDM unifies; with one issuer the link starts at the earliest filing (28 May, not the CUSIP holding's 5 June), so the first ruling is already whole with no primitive; with two mastered issuers the Security gets one ISSUED_BY link per issuer, no review. The primitive is not built; the remaining question is the operator's (below)
- [ ] Operator decision: a Security whose records name two issuers has two ISSUED_BY links today; inside one record two issuers give no link. Keep two links, or allow one issuer per Security and send the second to review
- [ ] Learning → skill (`security-master`, the fold): a count measured with removed code is not evidence; check the premise in the rules first
