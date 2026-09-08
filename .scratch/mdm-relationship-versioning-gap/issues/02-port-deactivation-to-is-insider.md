Type: task
Status: open

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

(not yet resolved)
