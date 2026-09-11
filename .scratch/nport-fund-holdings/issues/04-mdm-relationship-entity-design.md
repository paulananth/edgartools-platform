Type: grilling
Status: open

Blocked by: 01, 02, 03, 07

## Question

Should N-PORT holdings feed a new MDM relationship type (e.g.
`FUND_HOLDS`), or stay silver-only for this map's first landing (per the
"Not yet specified" note on the map about gold/MDM being possibly out of
scope for a v1)? **Note: "extend the existing `MdmFund`/`MANAGES_FUND`"
is no longer a live option** -- Ticket 07 confirmed `MdmFund` is scoped to
the Form ADV private-fund universe (keyed on `private_fund_id`), a
structurally different regulatory population from N-PORT's registered
funds; whatever new entity type(s) Ticket 07 lands on is what this
ticket's relationship design targets instead. If a relationship type is
warranted, how does it relate to the existing `INSTITUTIONAL_HOLDS` type
(adviser-holds-security, from 13F) -- same underlying real-world concept
(a fund/manager holding a security) viewed from a different filer's own
report, so double-representation risk needs a deliberate answer, not an
accident.

## Answer

(not yet resolved -- working framework sketched below, to be settled once
Ticket 07 lands the entity model)

Not every new entity connection needs to be a first-class
`mdm_relationship_type`/graph-synced edge -- this codebase already has a
precedent for the opposite: `MdmFund.adviser_entity_id` and
`MdmCompany.parent_company_entity_id` are both plain FK columns on the
entity table itself, populated at entity-resolution time, with
`MANAGES_FUND` then *derived from* `MdmFund.adviser_entity_id`
(`_derive_manages_fund`, `pipeline.py:2263-2267`) as a separate,
graph-queryable materialization of that same link -- so an FK-only
connection is a real, already-used option, not just a shortcut. Sorting
the candidate connections this way:

- **Registrant (Trust) -> Series (Fund) containment**: likely FK-only
  (a `registrant_entity_id` column on the new Series entity), same shape
  as `adviser_entity_id` -- no evidence yet that anyone needs to graph-
  traverse "which trust houses this fund" the way `INSTITUTIONAL_HOLDS`/
  `MANAGES_FUND` traversal is actually used for.
- **Series -> Share class** (if modeled as its own entity at all, per
  Ticket 07's open question): same reasoning, likely FK-only.
- **Series -> its own investment adviser**: real open question, not an
  obvious FK-only case -- could reuse `MANAGES_FUND` if the target side
  is widened to accept the new Series entity type (today's
  `_derive_manages_fund` is hardcoded to `MdmFund`), or could need a
  parallel mechanism. Depends on Ticket 07 confirming whether registered-
  fund advisers cleanly bridge onto existing `MdmAdviser`/`crd_number`.
- **Series (as a holder) -> Security (its constituent holdings)**: this
  IS the core new relationship this map exists for -- the N-PORT
  equivalent of `INSTITUTIONAL_HOLDS`, just from the fund's own report
  instead of a 13F manager's. Very likely needs its own new type (working
  name `FUND_HOLDS` in this ticket's original Question) rather than
  reusing `INSTITUTIONAL_HOLDS` outright, given the double-representation
  question already raised there and in Ticket 06.
- **Series (as a security) -> held by other entities** (a 13F filer's ETF
  position, a fund-of-funds holding another fund): needs **no new
  relationship type at all** -- once the Series entity has a correctly
  linked `MdmSecurity` row (`issuer_entity_id` pointing at the Series,
  per Ticket 07), the existing `INSTITUTIONAL_HOLDS`/`HOLDS` derivation
  logic already handles this unchanged, the same way it already handles
  any other issuer's securities.

Net working estimate, subject to Ticket 07 landing first: **one genuinely
new relationship type** (fund-holds-its-own-constituents), **one open
reuse-vs-extend question** (fund-to-adviser), and the rest resolved via
plain FK attributes rather than new graph relationship types.

**Cross-reference (added by a sibling map, does not resolve this
ticket):** [relationship-closing-pattern-framework](../../relationship-closing-pattern-framework/map.md)'s
[Ticket 03](../../relationship-closing-pattern-framework/issues/03-validate-against-nport-fund-holds.md)
is now resolved -- confirmed `FUND_HOLDS` should use the
`periodic_snapshot_diff` closing pattern (`docs/adr/0008-name-
relationship-closing-patterns.md`), the same one `INSTITUTIONAL_HOLDS`/
`MANAGES_FUND` already use, since N-PORT reports a fund's full current
holdings each quarter -- same reporting shape as 13F. **One real
implementation requirement surfaced by that validation, not yet
satisfied by anything in this map**: whoever implements `FUND_HOLDS`
needs its own N-PORT-specific amendment-supersession dedup (an
`NPORT-P`/`NPORT-P/A` equivalent of 13F's `base_sql` restatement filter)
*before* applying the closing pattern -- the pattern itself does not
dedupe amendments, it assumes its input already is deduped. This map's
own Ticket 01 already flagged N-PORT has "no built-in amendment-
supersession logic" -- that gap is exactly what a `FUND_HOLDS`
implementation would need to close first.
