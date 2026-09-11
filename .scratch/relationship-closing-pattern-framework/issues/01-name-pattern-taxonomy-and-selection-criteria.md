Type: grilling
Status: resolved

## Question

Across the codebase's five stateful relationship types, four
independently-written mechanisms already close a prior
`mdm_relationship_instance` version when a new fact arrives. Is there a
real, small taxonomy of pattern families behind them, and what's the
selection criterion for each -- so the next relationship type (or a
reviewer of an existing one) has a clear answer instead of writing a
fifth bespoke mechanism?

## Answer

Confirmed via grilling (two rounds: destination-shaping, then
taxonomy-confirmation) -- three real families, not four; the fourth
(`_derive_audited_by`'s inline closer) is a duplicate implementation of
family 2, not a genuinely distinct pattern (see Notes on the map for the
bug this duplication introduced).

1. **Value-signals-disposal** -- the new row's own value directly encodes
   "this relationship ended" (e.g. `shares_owned_after == 0`). Use when
   the source data carries an explicit in-band "this fact is now false"
   signal alongside the fact stream itself. Implemented today:
   `_deactivate_if_zero_shares` (HOLDS, COMPANY_HOLDS).
2. **Property-differs-from-prior** -- the new row is a point-in-time
   status snapshot for an already-fixed (source, target) pair; a
   differing property value means the prior status is now stale, not
   that a new fact has been added alongside it. Use for per-pair status
   fields with no explicit disposal signal (role/title, audit firm).
   Implemented today: `_deactivate_if_properties_changed` (IS_INSIDER,
   EMPLOYED_BY's exec/DEF-14A branch), plus `_derive_audited_by`'s own
   separate inline copy (buggy -- missing the chronological guard, see
   Ticket 11 on the parent map).
3. **Periodic-snapshot-diff** -- the source periodically reports its
   FULL current set of targets for a source entity; anything absent from
   the latest report closes, and even still-present targets roll forward
   to a fresh version each period (their properties, e.g. `quarter_end`,
   differ every period even when the underlying holding is unchanged).
   Use when a filing type reports a complete snapshot of a *set*, not a
   single pair. Implemented today: `_derive_institutional_holds_batch`'s
   roll-forward-to-latest-13F-period logic and
   `_derive_manages_fund_batch`'s expected-targets-diff (INSTITUTIONAL_HOLDS,
   MANAGES_FUND).

**Deliberately not chosen:** a full code unification/refactor collapsing
these three into one shared abstraction. Rule 0 (`/gof-refactor-reviewer`'s
own default) applies -- three small, independently correct,
low-churn implementations don't yet justify the migration risk. The
framework's job is to make the *selection* decision fast and
discoverable for the next relationship type, not to remove the
duplication that already exists safely.

**Enforcement:** a small declarative registry (`RELATIONSHIP_TYPES` ->
pattern name) plus a lightweight test asserting every relationship type
is classified -- not a refactor of the closing implementations
themselves. Confirmed via grilling over "prose-only documentation."

**Documentation location:** a new ADR under `docs/adr/` -- confirmed via
grilling over a `CONTEXT.md` glossary entry, since this is a hard-to-reverse,
surprising-without-context, real-trade-off decision per `/domain-modeling`'s
own ADR criteria.

Implementation (the actual ADR file + registry + test) is
[Ticket 02](02-write-adr-and-declarative-registry.md), not done here --
this ticket only settles the taxonomy and its enforcement/documentation
shape.
