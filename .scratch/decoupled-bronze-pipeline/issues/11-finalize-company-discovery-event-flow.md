# Finalize the company-discovery event flow

Type: grilling
Status: resolved
Blocked by: (none)

## Question

[Decide MDM's role in the decoupled architecture](06-decide-mdm-role-in-new-architecture.md)
surfaced this without answering it: company *discovery* (a new CIK
entering the tracked universe) is sourced from SEC's own company index
(ticker/company_tickers feeds) — not from a parsed filing or any
bronze-write event. **SEC's index is the system of record for which
companies exist and should be tracked** (universe membership) — distinct
from MDM being system of record for resolved entity *attributes* once a
company is known (ticket 06) and distinct from the bronze-write event
model [ticket 04](04-decide-event-granularity.md) is designing for
ongoing filings.

Today this flow is `seed-universe` (warehouse-side: reads SEC's index,
creates candidate company rows) → `mdm-seed-universe` (MDM-side: creates
the corresponding MDM entity) → `Stage0CompanyIdentity`/the
delta-then-reduce identity refresh folded into `WindowedBootstrap`
(stage0-stage1-consolidation map) — all synchronous, all inside the same
`load_history` execution that also does bronze/silver capture.

Finalize, for the decoupled architecture:

1. What triggers a discovery check against SEC's index — polling on a
   schedule, or is there a push/webhook signal SEC provides? (If polling:
   at what cadence, and does that cadence itself need to be event-driven
   or is a fixed schedule fine for a system-of-record feed that changes
   rarely relative to filing volume?)
2. What event does a detected change (new CIK, or a tracked CIK's
   universe-membership status changing) emit, and who consumes it —
   does it fan out directly to both `seed-universe` and
   `mdm-seed-universe`, or does one trigger the other sequentially?
3. Does discovering a new CIK need to *directly* trigger bronze capture
   for it, or does discovery only need to make the CIK "known" (seeded
   into silver/MDM), with bronze capture picking it up on whatever
   ongoing cadence [ticket 04](04-decide-event-granularity.md) settles on
   for already-tracked companies? (I.e. is a newly-discovered company a
   special first-capture case, or does it immediately become
   indistinguishable from any other tracked CIK once seeded?)
4. Does this reuse the same messaging substrate [ticket
   02](02-research-messaging-substrate-options.md) picks for bronze-write
   events, or is a low-volume, infrequent signal like this simpler to
   handle with different machinery (e.g. a scheduled Lambda/task diffing
   SEC's index, no message bus needed at all)?

## Answer

**Ownership consolidates onto MDM: seed-universe's fetch, dedup, and
cleaning all move into MDM's domain. Warehouse's role becomes purely
reactive.** Decided 2026-08-11.

**Today's actual flow, traced precisely (not as CLAUDE.md's diagram
simplifies it)** — read `warehouse_orchestrator.py:1721-1788` (warehouse
`seed-universe`) and `mdm/cli.py:1063-1128` (MDM `seed-universe`) in full:

1. Warehouse `seed-universe` fetches SEC's `company_tickers_exchange.json`
   directly, **dedupes by CIK itself** (`warehouse_orchestrator.py:1743-1750`,
   a plain seen-set loop), filters out CIKs MDM already reports active
   (`:1760-1770`, querying `_get_mdm_tracked_ciks`), then writes silver
   tracking rows (`_seed_silver_tracking_status`, `:1773-1777`, status
   `bootstrap_pending`) and a CIK batch file
   (`_write_cik_universe_batches`, `:1779-1786`) that Stage 1's
   `WindowedBootstrap` consumes as its work queue.
2. MDM `seed-universe` (`mdm/cli.py:1063`) defaults to `--source silver`
   — it imports whatever warehouse just wrote to silver into MDM's own
   entity/company tables. Its `--source edgartools` branch (`:1104-1124`)
   duplicates the *exact same* SEC-index-fetch-and-dedup capability
   warehouse's command already has, but is explicitly discouraged in its
   own output message: `"edgartools live ticker pull is not the Decision
   Subject Universe system of engagement; prefer --source silver after
   warehouse seed"`.

**This is duplicated capability with an inverted ownership arrow**: MDM,
the system of record for company data, currently *waits* on warehouse to
fetch and clean SEC's index first, then re-imports secondhand from silver
— rather than owning discovery itself and having warehouse react to it.

**Resolution:** promote MDM `seed-universe --source edgartools`'s path
(currently a discouraged fallback) to be the **primary** discovery
mechanism. Concretely:

1. **MDM owns the SEC-index fetch, dedup, and all cleaning** — the
   seen-CIK dedup loop, any future normalization (ticker casing, exchange
   mapping, etc.) moves into MDM's codebase. This is the same principle
   already established for entity resolution (ticket 06) and relationship
   derivation (ticket 10): MDM is where master-data cleaning happens, not
   downstream of it.
2. **MDM's `--source silver` re-import path is retired** — nothing left to
   import once MDM does its own fetch; the current two-hop
   fetch-then-reimport shape collapses to one hop.
3. **Warehouse's `seed-universe` command's fetch/dedup logic is retired.**
   What remains warehouse-side is purely reactive bookkeeping — the same
   two calls that already exist at the tail of today's function
   (`_seed_silver_tracking_status`, `_write_cik_universe_batches`), now
   triggered by an event MDM emits ("these CIKs are newly tracked") rather
   than by warehouse's own independent fetch. This directly answers the
   ticket's original question 2 ("does it fan out to both, or does one
   trigger the other") — neither; it becomes one MDM-owned step publishing
   an event, one warehouse-side reactive consumer.
4. **Question 3 (does discovery need to trigger bronze capture directly):**
   no — discovery's job ends at "MDM knows this CIK exists and publishes
   that." Warehouse's reactive consumer seeds silver's tracking status and
   the CIK batch file; actual bronze capture still runs on whatever cadence
   [ticket 04](04-decide-event-granularity.md) settles on for tracked
   CIKs generally. A newly-discovered company becomes indistinguishable
   from any other tracked CIK immediately after seeding, not a special
   first-capture case.
5. **Questions 1 and 4 (trigger cadence, messaging substrate) remain
   genuinely open** — this resolution settles *ownership and shape*, not
   the trigger schedule or which substrate carries the event. Given
   [ticket 02](02-research-messaging-substrate-options.md) just resolved,
   whoever picks this up next should default to reusing that substrate
   rather than introducing new machinery for a low-volume signal, but
   confirming that is follow-on work, not decided here.

**Cross-map implication, noted not resolved here:** this revises the
shape of two already-closed decisions in *other* maps —
`state-machine-consolidation`'s ticket 04 ("keep `mdm_seed_universe`
as-is, retire `mdm_seed_from_silver`") assumed today's two-hop shape as a
given; and `seed-universe-narrow-hydrate`'s ticket 05 (MDM as
system-of-record for the *novelty check* specifically) is a strict subset
of this broader consolidation. Neither closed ticket is wrong as far as it
went — this extends further than either anticipated. Flagging for whoever
implements this rather than silently reopening closed tickets in maps this
session didn't drive.
