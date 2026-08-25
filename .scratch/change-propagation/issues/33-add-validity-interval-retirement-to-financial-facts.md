# 33 — Add validity-interval retirement to financial facts

**What to build:** Decide and implement how `sec_financial_fact` (and any
sibling company-facts-scoped table that needs it) represents a fact that a
fresh, complete company-facts snapshot no longer contains — so that
retirement ("Changed, unchanged, reinterpreted, replayed, **and retired**
facts produce deterministic verified outcomes," Ticket 22 bullet 4) is a real,
tested outcome kind, not an unimplemented one.

**Blocked by:** None — the decision is standalone, though it should read
Ticket 22's Answer first for the constraint it already ran into.

**Status:** ready-for-agent

- [ ] Decide whether `sec_financial_fact` (and `sec_accounting_flag`, if it
  needs the same treatment) gains a `valid_from`/`valid_to`/`is_current`-style
  column, matching `.scratch/change-propagation/spec.md`'s "`RETIRE` closes
  the current validity interval with the causing source revision and scope
  proof. It never physically deletes history" rule — confirmed live that no
  such column exists today (`silver_store.py` ~line 599).
- [ ] Decide the comparison basis: a fact is "retired" when a CIK's fresh,
  COMPLETE company-facts snapshot's membership set (accession_number,
  concept, fiscal_period, segment, period_end, period_start) no longer
  contains a key that a prior complete snapshot's membership set did —
  `company_facts_silver_acceptance.py`'s `_member_digest`/`scope_reference`
  recording (Ticket 22) already computes the per-snapshot membership set this
  comparison would need; it just doesn't act on it today.
- [ ] Decide whether this is a per-CIK full-scope comparison (compare this
  snapshot's whole membership set against the immediately prior one for the
  same CIK) or something narrower.
- [ ] Implement the write path (a new merge/retire method on `SilverDatabase`,
  analogous to `stage_submission`'s scope-retire DELETEs but respecting the
  "never physically deletes" rule via the new interval column instead of a
  real DELETE) and wire it into `company_facts_silver_acceptance.py`'s
  `_finalize_company_facts_candidate`.
- [ ] Regression test: a second complete snapshot missing a fact key the
  first snapshot had produces a deterministic, verified "retired" outcome for
  that key, and the row's history remains queryable (not deleted).
