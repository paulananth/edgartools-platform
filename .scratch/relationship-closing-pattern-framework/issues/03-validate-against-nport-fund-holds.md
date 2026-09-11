Type: grilling
Status: open

Blocked by: 01

## Question

Apply Ticket 01's framework to the concrete near-term case: N-PORT's
prospective `FUND_HOLDS` relationship type (a fund/Series holding its own
constituent securities, reported quarterly per N-PORT filing -- see
`nport-fund-holdings`'s own
[Ticket 04](../nport-fund-holdings/issues/04-mdm-relationship-entity-design.md),
which independently concluded this is "very likely" a genuinely new
relationship type, structurally the fund-side mirror of
`INSTITUTIONAL_HOLDS`). Which of the three named patterns does
`FUND_HOLDS` fit, and does applying the framework to it surface anything
the framework itself needs to sharpen (a fourth pattern, an ambiguous
edge in the selection criteria, etc.)?

Record the answer here, then cross-link it as a comment/pointer on
`nport-fund-holdings`'s Ticket 04 for whoever resolves that ticket once
its own blockers (01/02/03/07 on that map) clear -- this ticket does not
resolve Ticket 04 itself, which is blocked on entity-design questions
unrelated to closing-pattern selection.
