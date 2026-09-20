# Company Legal-Entity Enrichment — GLEIF consumer specification

Owning workstream: Company legal entity (MDM Enrichment Program
[spec-index](../mdm-enrichment-program/spec-index.md)), first consumer of the
[Shared Enrichment Foundation](../../docs/specs/mdm-enrichment/shared-foundation.md).
Decision record: [GLEIF MDM enrichment evidence map](map.md), sixteen resolved
tickets (2026-09-11 → 09-12), written up here per
[ticket 17](issues/17-write-and-verify-gleif-mdm-spec.md) on 2026-09-19.

Status: **decision-complete for the Company consumer; not implementation
complete.** Written against a foundation spec that carries its own marked
*Open* items and two Clean MDM proposals awaiting review; each dependency is
named where it bites. Nothing here authorizes implementation; the
[release gates](#release-gates) do.

**Implementation owner.** Clean MDM's
[Company mastering completion gate](https://github.com/paulananth/edgartools-platform/blob/codex/clean-mdm-integration/docs/specs/clean-mdm/company-completion.md)
(`docs/specs/clean-mdm/company-completion.md` on `origin/codex/clean-mdm-integration`,
Codex/Grok-owned, read-only from here) already sequences GLEIF capture,
normalization, Company-to-LEI binding, field policy, relationships, and
daily/monthly update as its steps 2–8, and cites this map's tickets 13, 15,
and 16 as its accepted semantics. **This spec is the consumer contract that
delivery must satisfy; it does not re-plan the delivery.** Where this spec
and that gate disagree, the disagreement is a defect in one of them to be
raised by handover, not resolved by editing their file.

## Governing directive

Legacy MDM is being decommissioned. This consumer targets Clean MDM's
`mdm_v2` tables and Merge Stage only (`edgar_warehouse/mdm/clean/`). The
map's earlier evidence-level decisions (source authority, cadence, field
selection, first slice) name no target schema and survive unchanged; this
spec is where they meet `mdm_v2`.

## Vocabulary

As in [`CONTEXT.md`](../../CONTEXT.md): **Company Legal-Entity Enrichment**,
**GLEIF Evidence Capture**, **GLEIF Daily Delta Refresh**, **GLEIF Candidate
Backstop**, **GLEIF Full Reconciliation**, Enrichment Stewardship Decision,
Adjudicated Seed Link, Enrichment Business Retirement, Deferred Domain
Evidence, and the foundation's actors (Fetch Planner … Steward).

## Source authority

[Ticket 06](issues/06-lock-company-enrichment-source-authority-boundary.md):

- **SEC** is the Source Authority for filings, reported financials, and SEC
  identity. **CIK is the authoritative identifier.**
- **GLEIF** is the Source Authority for published Global LEI Index legal
  identity, lifecycle, registration, direct and ultimate accounting
  consolidation, and reporting exceptions. **LEI is additive evidence.**
- Fund, Branch, Adviser, Person, Security, market-price, and
  financial-calculation domains are outside this consumer.

Publication families consumed, per the foundation's taxonomy:

| Family | This consumer | Cadence |
| --- | --- | --- |
| GLEIF Golden Copy (Level 1 + RR + REPEX) | **required** | daily 24-hour delta; monthly full ([ticket 07](issues/07-set-gleif-source-refresh-frequency.md)) |
| OpenCorporates mapping | corroborating evidence only, never merge authority | bi-weekly ([ticket 11](issues/11-decide-gleif-identifier-mapping-routing.md)) |
| ISIN, BIC, MIC, QCC, GEM, CIQ mappings | **not consumed** — Security, Branch, Market/Venue, Government consumers | — |

Capture is source-wide ([ticket 09](issues/09-lock-shared-gleif-capture-boundary.md)):
the complete official publication is captured once and routed by GLEIF
category, relationship type, and identifier semantics. A record is never
inserted into Company because it has an LEI. Records outside this consumer's
scope are Deferred Domain Evidence: `mdm_v2.deferred_record` with an open
blocking review, retained, non-publishing.

Daily Company portfolio ([ticket 12](issues/12-decide-daily-company-source-portfolio.md)):
the existing SEC new-filing / impacted-CIK path, one official SEC ticker
snapshot, one GLEIF 24-hour delta. No other full-universe Company feed.

## Accepted identity evidence

[Ticket 13](issues/13-decide-accepted-link-publication-policy.md). A
Company-to-LEI binding may become an **active** `mdm_v2.decision`
(`operation = 'bind'`) only when one of:

1. It is an **Adjudicated Seed Link** — one of the 308 links from
   [ticket 02](issues/02-run-exhaustive-identity-comparison.md)
   (`research/02-decisions.jsonl`) — that **revalidates** against the
   selected current baseline; or
2. It is a **verified deterministic crosswalk** from an authoritative or
   certified identifier that passes domain semantics and one-active-binding
   uniqueness.

Everything else:

| Tier | Disposition |
| --- | --- |
| A (deterministic) | publishable per rule 2 |
| B, C (heuristic) | Steward review only — a candidate, never an unattended link (Tier B measured 90.0% accepted under review; not the 99.9% bar) |
| D | rejected, disposition recorded |
| exact or fuzzy **name match alone** | never sufficient, in any tier |

Uniqueness: one active LEI binding per Company, one active Company per LEI.
A conflicting candidate is a hard veto into review, never a silent rebind.

Revalidation triggers: changed LEI record, changed mapping, conflicting
candidate, successor/duplicate/retired LEI status, monthly reconciliation,
rule-version change. A failed link is **business-closed** (`operation =
'revoke'`), its decision preserved; a successor LEI needs a **new**
decision, never automatic rebinding.

The 308 seed links are seed evidence for *this* consumer's first slice; they
are not a matching rule, not calibration truth, and not production approval
(Clean MDM's `evidence.md` says the same).

Automatic matching stays disabled (Clean MDM Q11/Q16) until an independent
holdout proves a lower confidence bound ≥ 99.9% precision with zero
uniqueness violations ([ticket 16](issues/16-select-first-delivery-slice.md)).

## Source and MDM schemas

No consumer-specific tables. Everything lands in the foundation's existing
rows:

| Concept | Where |
| --- | --- |
| Captured files | `change_ledger.source_revision`, one row per file (L1, RR, REPEX, manifest), `source_family = 'gleif'` |
| Dataset contracts | `mdm_v2.dataset` rows `gleif.lei`, `gleif.relationship`, `gleif.reporting_exception`, `gleif.opencorporates_lei` (names per Clean MDM's `source-evidence.md`) |
| Every Level 1 / RR / REPEX record, source grain | `mdm_v2.assertion` keyed `(source_code, record_key = LEI or RR key, publication_key)` |
| Company-to-LEI binding | `mdm_v2.decision` (`bind` / `revoke` / `override`) |
| Company | `mdm_v2.identity` (`kind = 'company'`) + `mdm_v2.projection` |
| Consolidation edge | `mdm_v2.projection` (`object_type = 'relationship'`) |
| Out-of-scope GLEIF records | `mdm_v2.deferred_record` |
| Candidate awaiting Steward | the foundation's pre-merge candidate — *proposed to Clean MDM, awaiting review*; until then, the consumer's preview path |
| Checkpoint | `mdm_v2.checkpoint` — see [dependency](#dependencies) |

**Projected fields** ([ticket 15](issues/15-decide-attribute-survivorship-and-conflicts.md)),
first slice only — LEI and link status; legal form; legal jurisdiction;
entity status and LEI registration status; registration dates, managing
LOU, validation source; registration-authority identity; entity creation
date. **Retained as source evidence, not projected**: names, legal and
headquarters addresses, legal events, expiration fields, successor LEIs.
Each projected value carries source, assertion, rule version, and
observed/effective validity.

**Field authority.** SEC and GLEIF values describing *different* concepts
stay parallel (SEC state of incorporation is not GLEIF legal jurisdiction).
Comparable disagreement enters field-conflict review and **cannot overwrite
SEC evidence**; the five measured jurisdiction conflicts
([ticket 03](issues/03-measure-attribute-lift-and-conflicts.md)) are the
seed of that queue. Selection order is Clean MDM's accepted policy
(override → versioned source rank → effective time → publication time →
stable key); this consumer supplies its versioned rank, it does not invent a
second order.

**Relationships** ([ticket 10](issues/10-decide-gleif-relationship-type-routing.md),
[research](research/10-gleif-relationship-routing.md)):

| GLEIF type | Publishes as | When |
| --- | --- | --- |
| `IS_DIRECTLY_CONSOLIDATED_BY` | new typed Company→Company relationship, same name | both endpoints accepted Companies |
| `IS_ULTIMATELY_CONSOLIDATED_BY` | new typed Company→Company relationship, same name | both endpoints accepted Companies |
| `IS_INTERNATIONAL_BRANCH_OF` | captured; Branch consumer | never here |
| `IS_FUND-MANAGED_BY`, `IS_SUBFUND_OF`, `IS_FEEDER_TO` | captured; Fund consumer | never here |

Existing `HAS_PARENT_COMPANY` and `MANAGES_FUND` are **not** reused —
different source, direction, and meaning. Consolidation is **never**
interpreted as ownership, control, or a generic parent. A missing local
endpoint blocks the edge; no generic entity is created. A reporting
exception is retained with its reason and never read as "no parent."
Measured baseline: 30 of 308 accepted companies have consolidation
evidence, 262 have typed exceptions
([ticket 04](issues/04-measure-accounting-parent-evidence.md)).

## Temporal behavior

Inherited from the foundation and Clean MDM's `source-evidence.md`. GLEIF
supplies `InitialRegistrationDate`, `LastUpdateDate`, `NextRenewalDate`,
relationship period start/end, and the publication date; each maps to an
assertion's `effective_at` or `publication_key` under the `gleif.*` dataset
contract's declared time semantics. Load time never substitutes for a
missing effective time. A Level 1 change or a relationship period end is a
new assertion, never an overwrite.

## Conflict and review states

Clean MDM's `decision.operation` set, unchanged. This consumer's review
queues, all Steward-owned:

1. **Identity candidates** — Tier B/C, conflicting candidates, successor /
   duplicate / retired LEIs.
2. **Field conflicts** — comparable SEC-vs-GLEIF disagreement.
3. **Relationship endpoints** — a typed consolidation whose parent or child
   is not an accepted Company (stays blocked, not coerced).
4. **Deferred domain** — non-Company GLEIF categories (blocking review on
   `deferred_record`, resolved only by that domain's consumer).

Every queue item has a terminal disposition before the consumer may claim a
publication complete; ambiguity never disappears by dropping rows.

## Cadence and processing

| Job | Does | Cadence |
| --- | --- | --- |
| **GLEIF Daily Delta Refresh** | apply the 24-hour L1/RR/REPEX delta; revalidate affected active links; evaluate newly eligible or materially changed Companies. Does **not** rematch the universe. | daily ([ticket 08](issues/08-set-gleif-mdm-processing-frequency.md)) |
| **GLEIF Candidate Backstop** | re-evaluate unresolved and unmatched Companies | weekly |
| **GLEIF Full Reconciliation** | complete Golden Copy; prove source-to-MDM parity; the only path that may business-close by absence | monthly |

Three eight-hour Golden Copy publications per day are **not** polled; one
is captured.

## Replay and recovery

[Ticket 14](issues/14-decide-delta-gap-recovery.md), now the foundation's
general rule: Level 1, RR, and REPEX are checkpointed as one Golden Copy
family; OpenCorporates as its own. A delta is applied only when its metadata
and captured inventory prove overlap from the last applied baseline;
otherwise capture and reconcile a complete Golden Copy for that family
before its watermark moves. Missing, late, corrupt, discontinuous, or
partially applied input fails closed; one family never advances another.

The monthly proof binds complete source inventory and hashes to normalized
record counts, added/changed/retired dispositions, MDM projections,
deferred and review queues, downstream parity, and an independently
replayable run. Operator evidence names the failed continuity check and the
recovery path chosen.

Initial backfill is the current complete baseline plus revalidated seed
links — **not** an unreviewed match of the full MDM universe.

## Observability

Per run (`bookkeeping.pipeline_run`): files captured / verified; records
normalized / deferred / total (Clean MDM's `source_accounting` invariant);
candidates by tier and disposition; active bindings created / revoked;
field conflicts opened / closed; typed edges published / blocked on
endpoint; checkpoint per family before and after; continuity result. Alert
on: a family checkpoint unchanged past its cadence + 24 h; any
name-only-link count > 0; any duplicate active binding (should be
impossible; alert on the invariant, not the count). *Open (foundation)*:
metric names and SLO thresholds.

## Security

The foundation's actors and roles, no additions. Steward for this consumer
is a named person until the calibration bar is met; no deterministic rule is
authorized as Steward for identity decisions in the first slice. GLEIF bulk
data needs no credential; OpenCorporates mapping is a GLEIF-published file,
not an OpenCorporates API call. *Open (foundation)*: IAM for the Temporary
Bronze Stage and Source Artifact Archive.

## Retention

Foundation contract. GLEIF raw bytes follow Temporary Bronze Stage /
Source Artifact Archive; the latest verified complete Golden Copy is
archived, deltas are deleted after every required checkpoint passes.
Assertions, decisions, projections history, and run lineage are permanent.

## Costs

Baseline from the research corpus: the frozen 2026-09-11 Golden Copy is
three ZIPs (`research/01-gleif-snapshot-manifest.json` records sizes and
CRCs). *Open*: approved runtime / memory / storage / request budget, which
[ticket 16](issues/16-select-first-delivery-slice.md) lists as a release
gate and the program's retention-and-cost workstream owns.

## Migration and rollback

- No data migration. No new tables.
- Rollback of any batch is Clean MDM's reversal contract; rolling back a
  binding restores the prior projection and preserves the decision chain.
- Rollback proof is a release gate (below): reverse a committed daily delta
  and show the prior generation active, evidence intact.
- Cutover from legacy MDM's Company table is **not** this consumer's
  concern; legacy is being decommissioned under Clean MDM's own cutover
  plan (30-day rollback window per `company-completion.md`).

## Tests

Beyond the foundation's:

| Level | Proves |
| --- | --- |
| Unit | Tier classification is deterministic on the frozen corpus; name-only candidates never reach Tier A; uniqueness veto fires on a second candidate for a bound LEI |
| Unit | Field routing: SEC incorporation and GLEIF jurisdiction never collapse; comparable conflict opens review, never overwrites |
| Integration (PG16) | Seed-link revalidation against the pinned baseline reproduces 308 accepted / 103 rejected / 87 unresolved / 502 no-candidate ([ticket 02](issues/02-run-exhaustive-identity-comparison.md)) |
| Integration | A typed consolidation with one unaccepted endpoint blocks and creates no entity; a reporting exception never yields "no parent" |
| Integration | RR delta applied without the same date's REPEX is refused (foundation completeness) |
| Replay | Independent rerun of the frozen cohort yields identical candidates, classifications, aggregates, and hashes (`research/02-replay-verification.json` is the pattern) |
| Recovery | A gap in the Golden Copy family triggers full reconciliation for that family while OpenCorporates' checkpoint is untouched |

Synthetic fixtures are labeled and never count as calibration evidence.

## Release gates

From [ticket 16](issues/16-select-first-delivery-slice.md), all required:

1. Complete, hash-verified source inventory for the selected baseline.
2. Terminal disposition for every candidate in scope.
3. **Zero** name-only automatic links.
4. **Zero** duplicate active bindings.
5. Complete provenance on every projected value and edge.
6. Deterministic replay of the cohort.
7. Independent, fail-closed checkpoints per family — requires the
   foundation's per-family checkpoint key (see dependencies).
8. Exact applicable downstream parity (export / graph for the same
   generation).
9. Rollback proof.
10. Approved runtime / memory / storage / request cost.
11. Release Owner GO.

Plus the foundation's own gates, which this consumer inherits.

## Dependencies

| On | Status | Bites where |
| --- | --- | --- |
| Foundation spec | written 2026-09-19, not verified | every section |
| Clean MDM per-family checkpoint key | proposed, awaiting review | this consumer needs two families (Golden Copy + OpenCorporates) → release gate 7 cannot pass on today's DDL; a Golden-Copy-only slice could |
| Clean MDM pre-merge candidate table | proposed, awaiting review | Steward review of Tier B/C before commit; until then, preview-path review only |
| Clean MDM `company-completion.md` steps 1–8 | Codex/Grok, in progress | the implementation this contract is verified against |
| Foundation *Open* items (cost, SLOs, IAM, storage class) | open | release gates 10 and observability |

## Non-goals

- Fund, Branch, Security, Adviser, Government, Market/Venue, Person
  consumers — captured, routed, deferred; never published here.
- Any heuristic auto-linking before the 99.9% holdout bar.
- Reusing `HAS_PARENT_COMPANY` / `MANAGES_FUND`.
- Interpreting consolidation as ownership, control, or beneficial
  ownership.
- Changing the company-eligible identity universe contract.
- Implementation, deployment, scheduling, or any edit to Clean MDM's files.
