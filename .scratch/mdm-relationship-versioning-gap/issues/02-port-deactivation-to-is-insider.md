Type: task
Status: resolved

Blocked by: 01

## Question

Design and implement a closing/deactivation mechanism for `IS_INSIDER`
(`_derive_is_insider`, `edgar_warehouse/mdm/pipeline.py:1465`) so a
legitimate role/title change for an already-known (person, company) pair
(e.g. officer -> director on election to the board, or an officer-title
update) closes the prior open version instead of colliding with it as an
unresolvable same-source conflict and being silently quarantined.

Directly motivates the original question this map grew out of ("are we
capturing board members"): live prod data (see
[Ticket 01](01-root-cause-existing-fix-effectiveness.md) for the
measurement query) shows 72 real (person, company) pairs where `role`
itself flips (most commonly officer -> director, i.e. a genuine board
election), and the majority of those newer, more accurate rows are
quarantined -- so the "current" `IS_INSIDER` read keeps showing a stale,
superseded role indefinitely. Concrete example traced live: pair
`0c1628b8-.../9b23b1f3-...` shows officer (2024-10-16, current) -> director
(2025-10-08, quarantined) -> still director (2026-04-17, quarantined) -- the
person's board membership has been invisible in "current" reads for 1.5+
years despite two independent, corroborating Form 4 filings confirming it.

`IS_INSIDER` has no existing `close_relationship_version` call anywhere in
its derivation method (confirmed via source read) -- unlike
`HOLDS`/`COMPANY_HOLDS`/`INSTITUTIONAL_HOLDS`, which PR #568 already gave a
bespoke closing rule each. `IS_INSIDER` has no equivalent "shares reach
zero" or "latest 13F CUSIP set" signal to hang a closing rule off of --
this ticket needs to design what "close the prior version" means for an
insider-role snapshot specifically (candidates to weigh: always close the
prior open version for the pair whenever a new filing reports different
properties for it, since a Form 3/4/5 amendment is inherently a
point-in-time snapshot of current status, not an additive fact; vs. some
narrower per-field rule). Should reuse Ticket 01's findings on whether the
existing `HOLDS`/`COMPANY_HOLDS`/`INSTITUTIONAL_HOLDS` patterns are
actually sound before modeling this one on them.

## Answer

Chose the ticket's leading candidate: always close the prior open version
for a (person, issuer) pair whenever a new filing reports different
properties (role, title) for it, since a Form 3/4/5 amendment is a
point-in-time snapshot of current status, not an additive fact.

**Implementation.** New instance method,
`_deactivate_if_properties_changed` (`edgar_warehouse/mdm/pipeline.py`),
mirroring the existing HOLDS/COMPANY_HOLDS zero-shares-close pattern's
shape (`_current_open_versions_by_pair`/`_track_open_version`, the same
shared infrastructure, unmodified) but with a different trigger and
contract: closes a candidate when its properties differ from the new
row's, using the *exact* discriminator `ensure_relationship`'s own
conflict check uses (`properties != new_properties`) so the two pieces of
logic never disagree about what counts as "different." Unlike the
zero-shares helper, this never signals the caller to skip
`ensure_relationship` — a role change is a new fact to represent, not a
disposal, so the new version is always still inserted afterward. Wired
into `_derive_is_insider` in both branches (ordinary incremental and the
`issuer_ciks`-scoped targeted-resync path) — a role change matters
regardless of which code path triggered the derivation.

**Real correctness gap found during the `/gof-refactor-reviewer` design
consult** (not present in the original candidate design, incorporated
before any code was written): nothing in the naive design accounted for
*chronological order*. Reprocessing an older row while a newer version is
already open — a late-filed amendment with an earlier `period_of_report`,
or exactly the `issuer_ciks`-scoped branch's own full-history rescan
revisiting historical filings — could incorrectly close the newer,
already-correct version using the stale row's earlier date. Fixed by only
closing a candidate when the new row's `effective_from` can be
*positively confirmed* at or after the candidate's own `valid_from_date`;
any ambiguity (either date missing) defaults to leaving it open, letting
the stale row fall through to `ensure_relationship`'s own conflict
machinery instead.

Tests: 4 new in `tests/mdm/test_pipeline_relationships.py`
(`TestIsInsiderDeactivation`) — a role change closes the prior version and
opens a new, non-quarantined one (the traced officer→director example
this ticket exists for); an identical re-filing at a later date leaves
everything open (control, proving the fix doesn't over-trigger); the
chronological guard itself (reprocessing an older row never closes an
already-open newer version); and the `issuer_ciks`-scoped resync branch
gets the same deactivation. Found and fixed a real gap in the shared
`StubSilver` test double along the way (its generic `IN (...)`-clause
row filter only recognized MANAGES_FUND's CRD field shape, silently
returning zero rows for any other type's `IN`-scoped query, including
IS_INSIDER's own `issuer_ciks` branch) — widened with a safe, ordered
fallback to also recognize `issuer_cik`.

## 3-axis code review

Ran the mandatory 3-axis `/code-review` (Standards/Spec/GoF). All three
came back clean — no hard violations, no correctness gaps, no structural
issues. Two minor findings fixed:
- **Spec:** the new method's docstring claimed "IS_INSIDER/EMPLOYED_BY
  deactivation," but this diff only wires it into `_derive_is_insider` --
  EMPLOYED_BY is Ticket 03's job, not touched here. Corrected the
  docstring to say it's designed for reuse there, not that it's already
  done.
- **Standards:** 3 of the 4 new tests unpacked `_seed_pair`'s return tuple
  without using it. Cleaned up (kept the unpack only in the one test that
  actually needs the entity IDs).

Full `tests/mdm/` suite: 704 passed. Full repo suite: pending final
re-run after the two review fixes above (last full run before them:
clean, only the 8 pre-existing unrelated Postgres-integration failures
this repo's test suite always shows without a local Postgres).

**Not yet done:** commit, deploy.
