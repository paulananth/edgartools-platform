Type: task
Status: resolved

Blocked by: 01

## Question

Design and implement the equivalent closing/deactivation mechanism for
`EMPLOYED_BY` (`_derive_employed_by`, `edgar_warehouse/mdm/pipeline.py:3400`)
that Ticket 02 designs for `IS_INSIDER` -- same root cause, different
source shape (`sec_executive_record`/DEF 14A compensation table +
`sec_employment_event`/8-K Item 5.02, two independently-watermarked source
tables per this method's own docstring, vs. `IS_INSIDER`'s single source).

Live evidence: `EMPLOYED_BY` shows 51.7% overall quarantine, and 97.8%
(6,767 of 6,919) for rows created since PR #568 landed -- the highest
post-fix rate of any type, since (like `IS_INSIDER`) it has zero existing
deactivation logic and every genuine year-over-year compensation or title
update for an already-known (person, company) pair is a same-source
conflict by construction.

## Answer

`_derive_employed_by` has two independent source branches under one call.
Only the exec/DEF 14A branch (`sec_executive_record`) needed a fix — the
event/Item 5.02 branch (`sec_employment_event`) already has its own,
pre-existing, separately-tested closing mechanism
(`_current_employment_versions` plus its own chronological guard), unrelated
to PR #568 or this map, and was left untouched.

**Implementation.** Reused Ticket 02's `_deactivate_if_properties_changed`
helper exactly as designed. Primed `current_by_pair =
self._current_open_versions_by_pair(sync_engine, "EMPLOYED_BY")` once before
the exec loop (EMPLOYED_BY is not in `_SELF_PRIMING_RELATIONSHIP_TYPES`, so
it's already unscoped-primed by the uniform dispatcher). Hoisted the
`properties` dict to a local variable (previously inlined directly into the
`ensure_relationship` call) so the exact same dict object is used for both
the deactivation discriminator and `ensure_relationship`'s own conflict
check — the same "never disagree" principle Ticket 02 established. Called
`_deactivate_if_properties_changed` before `ensure_relationship`, then
`_track_open_version` after.

Since `fiscal_year`/`source_accession` are both part of `properties`, they
always differ across two DEF 14A filings for different fiscal years — so
this closes and reopens on *every* subsequent year, not just genuine
role/comp changes. This is deliberate, not a looser-than-intended
discriminator: a DEF 14A comp record is inherently period-scoped (a new
fiscal year is a new fact about a different period), and narrowing the
discriminator to exclude those fields would desync it from
`ensure_relationship`'s own full-properties conflict check, reintroducing
the exact quarantine bug this ticket exists to fix (verified by tracing
`ensure_relationship`'s `clean_properties` comparison in `graph.py`).

**`/gof-refactor-reviewer` design consult (pre-code):** confirmed the reuse
was justified (the helper was explicitly generalized for this exact second
caller in Ticket 02) and confirmed no visibility/staleness risk from having
two independent "current open version" mechanisms (the exec branch's primed
cache, the event branch's live per-pair query) running sequentially in one
method — SQLAlchemy's default autoflush makes the exec branch's writes
visible to the event branch's subsequent live queries, and neither branch
reads the other's state structure directly.

Tests: 3 new in `tests/mdm/test_pipeline_relationships.py`
(`TestEmployedByExecDeactivation`) — a new fiscal year closes the prior
version and opens a new one (the fix's core case); an idempotent rerun of
an identical row does not close anything (control, proving the fix doesn't
over-trigger on true duplicates); the chronological guard (reprocessing an
older fiscal year never closes an already-open newer version, mirroring
IS_INSIDER's own guard test).

## 3-axis code review

Ran the mandatory 3-axis `/code-review` (Standards/Spec/GoF). One real
finding, confirmed independently by all three axes, fixed before commit:
`_deactivate_if_properties_changed`'s own docstring still read "designed
for reuse by EMPLOYED_BY too, per Ticket 03, but not yet wired there" —
false as of this diff, which is exactly that wiring. Corrected.

Two smaller findings, also fixed:
- **Standards:** the root-cause rationale was written out twice,
  near-verbatim, in the docstring and in an inline comment at the call
  site. Tightened the inline comment to cross-reference the docstring
  instead of restating it.
- **Standards:** the chronological-guard test hand-reimplemented
  `_ensure_proxy_person`'s UUID5 stub-derivation instead of calling the
  real helper -- a drift risk if that derivation ever changes. Fixed by
  calling `_ensure_proxy_person` directly to derive the test's person id.

**Spec** additionally verified, as a positive check (no fix needed): the
diff passes the literal same `properties` dict object to both the
deactivation check and `ensure_relationship`'s own `properties=` argument
(no independently-constructed second dict, no drift risk) — confirmed
correct per Ticket 02's stated discriminator-identity principle.

Full `tests/mdm/` suite green: 707 passed. Full repo suite green: 3167
passed, 8 failed (the same pre-existing, unrelated Postgres-integration
gaps this repo's suite always shows without a local Postgres), 7 skipped.

**Not yet done:** deploy.
