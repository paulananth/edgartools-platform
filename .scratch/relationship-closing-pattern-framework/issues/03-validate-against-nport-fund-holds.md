Type: grilling
Status: resolved

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

## Answer

**`FUND_HOLDS` fits `periodic_snapshot_diff`** -- the same pattern
`INSTITUTIONAL_HOLDS`/`MANAGES_FUND` already use. N-PORT (per
`nport-fund-holdings`'s own Ticket 01/02) reports a fund's FULL current
portfolio holdings as of each quarterly reporting period end, exactly the
same real-world reporting shape as a 13F filing (a manager's full current
position set) -- not a single-pair status update, and not a row that
itself signals disposal. `nport-fund-holdings`'s own Ticket 04 already
characterizes `FUND_HOLDS` as "the N-PORT equivalent of
`INSTITUTIONAL_HOLDS`, just from the fund's own report instead of a 13F
manager's" -- this validation confirms that structural analogy extends to
the closing pattern, not just the entity direction.

**This validation surfaced one real gap in ADR 0008, now fixed there
(see the ADR's own amendment)**: the `periodic_snapshot_diff` description
didn't previously distinguish the pattern's own roll-forward/close logic
from a PREREQUISITE the caller must separately provide -- amendment
supersession. `_derive_institutional_holds`'s `base_sql` filters out
superseded 13F rows via a `NOT EXISTS (... amendment_type = 'restatement'
...)` clause *before* the roll-forward logic (`_derive_institutional_holds_batch`
proper) ever sees the data; the pattern's actual closing/rolling logic
never re-derives "which row is the current one for this period" itself,
it trusts its caller already resolved that. `nport-fund-holdings`'s own
Ticket 01 already flagged N-PORT has "no built-in amendment-supersession
logic (warehouse-side work, same as other multi-amendment forms)" --
without this clarification, a future `FUND_HOLDS` implementer could
reasonably assume adopting `periodic_snapshot_diff` alone handles N-PORT's
own `NPORT-P`/`NPORT-P/A` amendment relationship, when in fact they'd need
to write their own equivalent amendment-dedup filter first, the same way
13F's ingestion already does. Sharpened in ADR 0008's `periodic_snapshot_diff`
bullet.

**Not a concern for closing-pattern selection specifically** (correctly
out of this ticket's scope, `nport-fund-holdings` Ticket 04's own
problem): the double-representation risk if the same security is both a
13F manager's holding and a fund's own N-PORT-reported holding.
`_index_open_relationship_versions` scopes open-version tracking by
`(rel_type_id, source_entity_id)`, so `INSTITUTIONAL_HOLDS` and
`FUND_HOLDS` edges against the same target security never collide at
the closing-pattern level even before that identity question is
answered -- each relationship type's periodic-snapshot-diff instance is
independent.

Cross-linked into `nport-fund-holdings`'s Ticket 04.
