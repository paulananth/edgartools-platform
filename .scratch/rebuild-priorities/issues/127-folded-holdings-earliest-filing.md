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

- [ ] Count the folded Securities whose start or issuer would change (from ticket 120's test run)
- [ ] Choose: an engine primitive (`earliest` over values; members over two groups), or accept with the count
- [ ] Learning → skill (`security-master`, the fold)
