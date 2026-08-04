# 92 — Decide F11's real data source (accounting flag / auditor DEI concepts)

Type: task
Status: open

## Question

[Ticket 42](42-decide-execute-fundamentals-backfill.md) found `sec_accounting_flag` (F11)
cannot be populated from `bootstrap-fundamentals --mode entity-facts` as currently designed:
`parse_entity_facts` (`edgar_warehouse/parsers/financials.py`) builds base rows exclusively
from four DEI XBRL concepts (`AuditorFirmId`, `AuditorName`, `AuditorLocation`,
`IcfrAuditorAttestationFlag`) — live-confirmed these are **never present** in
`data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` for any filer, Apple included. This is a
structural gap in the source, not a bug in the parser logic itself (SEC's aggregated
companyfacts endpoint doesn't surface these tags the way it does core financial concepts).

The cross-period forensic scores (Beneish M-score, Altman Z-score, Piotroski F-score,
`backfill_accounting_flags` in `edgar_warehouse/parsers/accounting_flags.py`) are a separate,
working code path -- they compute correctly from `sec_financial_derived`, but currently have
no `sec_accounting_flag` base row to attach to (see ticket 42's masking-bug fix, which stopped
that gap from being silently hidden, but didn't create the missing rows).

## What needs deciding

1. **Where should the 4 auditor DEI concepts + the forensic scores actually live/come from?**
   Candidates: (a) parse them from the 10-K's own per-filing XBRL instance document (the same
   byte-preserving fetch path `bootstrap-fundamentals --mode per-filing` already uses for
   earnings/proxy data) instead of the aggregated companyfacts API; (b) a different SEC
   endpoint/dataset that does surface these DEI tags; (c) decide the base row doesn't need
   auditor DEI fields at all -- restructure so `backfill_accounting_flags`'s forensic scores
   can write their own base row keyed on (cik, accession_number) directly from
   `sec_financial_derived`, without waiting on a DEI-sourced row that may never come from any
   source at reasonable cost.
2. Whatever's decided, needs a real live validation the same way tickets 42's F4/F5 passes
   were validated -- values checked against a real company's actual audit/attestation data, not
   just non-zero row counts.

## Done when

A data-source decision is made and either implemented + live-verified, or explicitly deferred
with a documented reason (e.g., cost/value tradeoff doesn't justify it yet).
