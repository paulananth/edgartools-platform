Type: task
Status: open

## Question

Should `INSTITUTIONAL_HOLDS` derivation (`_ensure_security_by_cusip`,
`edgar_warehouse/mdm/pipeline.py:3271`) link the CUSIP-stub securities it
creates to their issuer `MdmCompany` row, and if so, how -- given 13F
holdings report issuer identity as CUSIP + free-text `issuer_name`, with no
shared key against the Form-4-derived security universe?

Note: this is a distinct root cause from this map's main quarantine-versioning
finding (Tickets 01-05) -- an entity-resolution completeness gap (a missing
FK link), not a relationship-instance conflict/quarantine bug. Filed here at
the user's direction since it surfaced from the same investigation thread
(INSTITUTIONAL_HOLDS derivation, mdm-run-throughput Ticket 07's CUSIP work)
rather than because it shares the destination.

## Context

Confirmed live in prod MDM Postgres, 2026-09-08. `_ensure_security_by_cusip`
creates a `MdmSecurity` stub with `canonical_title`/`cusip`/`security_class`
but never sets `issuer_entity_id` -- neither on the create path nor the
existing-lookup path (full function body confirms no `issuer_entity_id`
reference anywhere).

**All 1,718 CUSIP-stub securities in prod have `issuer_entity_id = NULL`
(100%)** -- confirmed via
`SELECT (issuer_entity_id IS NOT NULL), count(*) FROM mdm_security ms JOIN
mdm_entity me ON me.entity_id = ms.entity_id WHERE me.resolution_method =
'cusip_stub' GROUP BY 1` -> `(False, 1718)`.

Concrete example (Apple, cik=320193, `MdmCompany.entity_id=478fcda2-...`):

| security | cusip | issuer_entity_id | resolution_method |
|---|---|---|---|
| Common Stock [f1] | NULL | `478fcda2-...` (correct) | `issuer_title_dedup` (Form 4) |
| Common Stock | NULL | `478fcda2-...` (correct) | `issuer_title_dedup` (Form 4) |
| Restricted Stock Unit [f1] | NULL | `478fcda2-...` (correct) | `issuer_title_dedup` (Form 4) |
| Apple Inc. | `037833100` | **NULL** | `cusip_stub` (13F) |

The 13F-derived "Apple Inc." security and the three Form-4-derived
securities represent the same real-world issuer's securities but are
disconnected `mdm_security` rows with no relationship between them.

**Why the obvious fixes don't trivially work:**
- The only existing issuer-linking mechanism, `backfill_security_issuers`
  (`pipeline.py:2496`), matches securities to issuers by `canonical_title`
  against Form-4 `security_title` text ("Common Stock", "Restricted Stock
  Unit", etc.) -- a 13F stub's `canonical_title` is the issuer's *name*
  ("Apple Inc."), never a Form-4-style security-title string, so this
  mechanism structurally cannot match a CUSIP-stub security.
- Cross-referencing by CUSIP itself isn't viable either: confirmed via
  `SELECT resolution_method, count(*), count(*) FILTER (WHERE cusip IS NOT
  NULL) ... GROUP BY 1` that **zero** Form-4-derived (`issuer_title_dedup`)
  securities have a `cusip` value populated at all -- the ownership silver
  tables (`sec_ownership_non_derivative_txn`/`_derivative_txn`) have no
  `cusip` column in their schema (`silver_store.py` -- only
  `sec_thirteenf_holding` carries one), so there is no shared CUSIP key
  between the two security universes today.
- `issuer_name` (13F's free-text issuer name) is currently used only to set
  `canonical_title` on the stub (`pipeline.py:3361`) -- never used to look
  up or match against `MdmCompany.canonical_name` anywhere in the codebase
  (confirmed via grep, no other reference exists).

**Downstream consequence:** `_derive_issued_by` (`pipeline.py:2473`) only
processes securities with `issuer_entity_id IS NOT NULL`, so every
13F-derived CUSIP-stub security -- funds/ETFs and any issuer without
SEC-reporting insiders included -- is permanently excluded from `ISSUED_BY`,
and any "which company issued this security" traversal (including the
graph) dead-ends at an orphan security node for these holdings.

## Answer

(not yet resolved -- candidate fix directions to weigh: fuzzy-match
`issuer_name` against `MdmCompany.canonical_name` at stub-creation time
despite lower reliability than an exact key; populate `cusip` on Form-4
securities where available and rely on the existing CUSIP-lookup branch
instead/in addition; or accept the gap as a known limitation and only
backfill it for securities a fund materially holds, given no
authoritative CUSIP-to-CIK crosswalk is available to this system)
