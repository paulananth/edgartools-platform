# Lock what usable identity means for v1 insiders and employment

Type: grilling
Status: open
Blocked by: 02, 03

## Question

Given live IS_INSIDER and EMPLOYED_BY inventory, what must be true for
those v1 sections to count as usable Agent-Grade Input Facts — graph
edges only, or also gold identity columns / coverage over the Decision
Subject Universe?

At minimum decide:

1. Whether graph-keyed current edges with the ticket 05 source rules are
   sufficient input, even when gold `OWNERSHIP_HOLDINGS` has no
   `OWNER_CIK` / `OWNER_NAME`.
2. Whether a section can be `empty` for most of the universe and still
   count as sorted-out input (coverage is a flag, not a fill-every-CIK
   job).
3. Whether any gold-column or silver-to-gold identity work is in this
   map, or is deferred to Agent Decision Contract SQL.

Predecessor: [Lock issuer v1 agent-grade bundle sections](../../agent-decision-contract/issues/05-lock-issuer-v1-agent-grade-sections.md)
already locked graph-keyed `present` / `empty` / `unavailable`. This
ticket binds that rule to the live completeness facts from tickets 02
and 03.

## Comments

- 2026-09-11 research 02/03: live `EMPLOYED_BY.SOURCE_SYSTEM` is
  `item_502_filing` (4,268) and `proxy_filing` (45), not the ticket 05
  tokens `item_5_02` / `proxy_def14a`. Include that token decision here.
