# Decide MDM's role in the decoupled architecture

Type: grilling
Status: resolved
Blocked by: 03 (resolved — this ticket is now unblocked)

## Question

Does MDM become its own independent async consumer of silver-write events
(entity resolution + relationship derivation reacting to new silver rows),
or does gold now wait on a separate MDM-completion signal distinct from
silver's? Informed by ticket 03's factual mapping of which gold
tables/columns actually depend on MDM output — if MDM dependency is
concentrated in a few tables, MDM might be a narrow, optional downstream
consumer rather than a universal gate.

**Inherited findings from [Map which gold tables depend on MDM
output](03-research-mdm-gold-dependency-mapping.md) (2026-08-11):**

- MDM dependency is narrower than the question above assumed: **0 of 28**
  Python gold builders touch MDM at all; exactly **1** real gold surface
  (`EDGARTOOLS_GOLD.COMPANY`) depends on it, via a `LEFT JOIN` enrichment
  on MDM's entity-resolution output — not on `backfill-relationships` or
  any relationship type. This strongly supports "narrow, optional
  consumer," with one carve-out: the Decision Contract's
  `SUBJECT_FEATURE_SCREEN`/Agent View has a hard, non-optional filter on
  `tracking_status='active'` (no NULL-tolerant fallback) — that one surface
  needs MDM's entity resolution to have already run for a given company,
  and any design must decide whether it accepts a temporarily-smaller
  Decision Subject Universe or gates that surface separately.
- **Scope correction: this ticket is about MDM's role relative to *gold*.**
  Graph sync turned out to be a *distinct* decoupling boundary, not a
  sub-question of this one — see the note added to [Decide the
  completeness/watermark signal](07-decide-completeness-watermark-signal.md).
  Don't fold graph sync's consumer contract into this ticket's answer;
  answer this one for gold specifically.

## Answer

**MDM becomes an independent, async, event-driven consumer — the system of
record for all master data — and gold never blocks on it, except one
surface that explicitly gates on it.** Decided 2026-08-11.

**Principle (governs all of the below):** MDM is the system of record for
master data, not merely an optional enrichment source. This is already
partially load-bearing in the code today — `company.sql`'s
`coalesce(m.canonical_name, c.entity_name)` already treats MDM's resolved
value as authoritative when present, silver's raw value as a fallback only
for not-yet-resolved companies. The principle applies to all **5** domains
MDM resolves (`export_pending`'s `DOMAIN_TO_TABLE`: company, adviser,
person, security, fund), not just company — even though ticket 03 found
only company has a live dbt consumer today. Locking the principle now
costs nothing (it's documented intent, not new code); wiring
adviser/person/security/fund consumption is separate, unscheduled
follow-on work this map acknowledges but does not schedule.

**Concrete answers:**

1. **MDM's entity resolution (`mdm run`) runs as an independent async
   consumer of silver-write events**, on its own cadence, decoupled from
   gold's schedule entirely. This is the standard system-of-record shape:
   MDM owns writes to master data, publishes canonical state as it
   resolves, consumers subscribe/pull when ready — not a synchronous
   gate any consumer waits inside.
2. **Gold does not wait on MDM** for the Python layer (28/28 tables) or 21
   of 23 dbt models (ticket 03) — this was already true given today's
   `LEFT JOIN` tolerance and is now formalized as the design principle,
   not just an incidental tolerance.
3. **Exception, explicit, not silent:** the Decision Contract's
   `SUBJECT_FEATURE_SCREEN`/Agent View gets its own readiness gate on
   "MDM has resolved this company," separate from gold's own freshness
   signal — because that surface genuinely requires the authoritative
   master-data record, and "silently absent from an evidence-gated agent
   surface" is a worse failure mode than "explicitly not-yet-ready." Feeds
   ticket 07's watermark design as a third signal (alongside silver/gold
   and graph), not invented separately there.
4. **Relationship derivation (`backfill-relationships`) stays out of this
   ticket's scope** — ticket 03 confirmed zero relationship types reach
   gold; that cadence is purely a graph-sync design question. Graduates
   into its own ticket (see below), mirroring this one but for graph.

**Additional requirement (2026-08-11): must seamlessly support seed
universe.** Company *discovery* — a new CIK entering the tracked universe
via `seed-universe`/`mdm-seed-universe` — is a genuinely different event
source from the "silver row changed" events (1)-(3) above assume: it's
sourced from SEC's company index (ticker/company_tickers feeds), not from
a parsed filing, and today runs as part of the same synchronous
Stage-0-style flow bronze/silver capture depends on (per
stage0-stage1-consolidation, now folded into `WindowedBootstrap`'s
delta-then-reduce identity refresh). For MDM's new async role to
"seamlessly support" this, entity discovery must be a first-class event
MDM's consumer handles the same way it handles resolution/update events —
not a special synchronous bootstrap case bolted onto the new architecture.
**This is a genuine open design question this ticket surfaces but does not
answer** — whether "new CIK discovered" is the same event type [Decide
event granularity for bronze-write triggers](04-decide-event-granularity.md)
is designing for, or a distinct upstream event source that ticket needs to
account for separately. Noted there rather than answered here, since it's
about event *sourcing*, not MDM's role once an event arrives.

**Graduated ticket:** graph sync's own async-consumer role (relationship
derivation's cadence, `sync-graph`/`verify-graph`'s trigger) is real,
sharp-enough-to-state fog per point 4 above — will be ticketed as its own
grilling question, mirroring this one, on the next pass over this map.
