# Decide whether the v2 layer needs a second relationship-edge store

Type: grilling
Status: claimed
Blocked by: 09

## Question

[Survey free/public serving options for the v2 relationship-edge layer](09-survey-relationship-edge-serving-options.md)
found no candidate (SPARQL/RDF, hosted property-graph, GraphQL-over-HTTP,
static-JSON) that clears the free-tier + public-reachability bar as
cleanly as Atlas M0 already does — and confirmed `IS_INSIDER`/
`EMPLOYED_BY` are **already** served today, embedded in the existing
Mongo `issuer_subject_bundle` document (ticket 04). This is not "where
do edges live" — it's whether that embedding is good enough, or whether
a real access-pattern gap justifies a second store despite every
option's downside.

Lock:

1. Does a v2 agent need **reverse/multi-hop graph lookups** (e.g. "which
   issuers is person X an insider of", "who else works where this
   person's employer's other insiders work") that Mongo's per-subject
   embedded shape cannot serve without a second, separately-materialized
   index collection? Or does v2's agent access pattern stay "start from
   a CIK, read that issuer's neighborhood" (which Mongo already serves)?
2. If (1) finds a real gap: is it worth adding a second store given the
   survey's downsides (AuraDB Free's 30-day auto-delete, Hasura's
   backing-Postgres pause behavior, static hosting's point-lookup-only
   shape, SPARQL having no confirmed free host at all) — or is a
   same-store fix preferable (e.g. a second Mongo collection indexed by
   person/employer instead of by issuer, still Atlas M0, no new vendor)?
3. If a second store is warranted: which one, and does adding it reopen
   ADR 0009 (which currently names Mongo as *the* v2 serving target) —
   or does ADR 0009 get amended to add a second, narrower-scope
   projection rather than being superseded outright?
4. If no second store is warranted: does this ticket's answer become the
   record that closes the SPARQL/RDF question for v2 (with a pointer
   back to this map's Notes reopening), or does "not yet, revisit if
   access patterns change" leave it open as fog for later?

## Comments
