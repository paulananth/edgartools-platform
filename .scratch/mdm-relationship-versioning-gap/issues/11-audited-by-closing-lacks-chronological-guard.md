Type: task
Status: open

## Question

`_derive_audited_by` (`edgar_warehouse/mdm/pipeline.py:4085-4101`) has its
own inline closing mechanism for a changed auditor: when `auditor_changed`
is true, it directly queries and closes every open AUDITED_BY version for
the company pointing at a *different* audit firm than the new row.

Unlike `_deactivate_if_properties_changed` (the shared helper IS_INSIDER/
EMPLOYED_BY use for the same "close on differing new value" concept,
Tickets 02/03 on this map), this inline copy has **no
`confirmed_chronologically_after` guard**. That guard exists specifically
because a late-filed amendment or a full-history resync/reconciliation
pass can revisit an OLDER row after a newer, already-correct version is
already open -- without the guard, reprocessing that older row would
incorrectly close the newer version using a stale date.

Fix this the same way Ticket 02 fixed it for IS_INSIDER: either add the
missing guard directly to `_derive_audited_by`'s inline query, or (likely
cleaner, and what `relationship-closing-pattern-framework`'s Ticket 02
assumes will happen) route AUDITED_BY through the existing
`_deactivate_if_properties_changed` helper instead of maintaining a
separate inline copy -- eliminating the duplication that let this bug
diverge from the already-fixed sibling in the first place.

This is a live, un-investigated bug (found while charting the
[relationship-closing-pattern-framework map](../relationship-closing-pattern-framework/map.md),
explicitly ruled out of that map's scope as a correctness fix rather than
a design question) -- not yet reproduced against real prod data or
confirmed to have actually caused a wrong closure in practice. Whoever
picks this up should confirm real impact (a live query for AUDITED_BY
rows closed by an out-of-order reprocessing event) before or alongside
the fix, per this repo's `/diagnosing-bugs` discipline.

## Answer

(not yet resolved)
