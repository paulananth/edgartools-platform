# Capture the reporting-owner evidence the Person contract needs, from bronze

Type: task
Status: resolved (2026-09-21) — code on `claude/person-ticket-19`; the re-export happens on the next ownership artifact run (PARSER_VERSION 3 is version-gated), after `20_silver_landing_ownership_evidence.sql`
Blocked by: none

## Resolution

The parser no longer calls edgartools' `Ownership.from_xml`, which fetched
every reporting owner's SEC submissions **live at parse time** (one request
per owner, outside every fetch policy) only to decide whether to reverse
the name. It reads the `ownershipDocument` XML directly and takes a
`submissions_lookup` the orchestrator builds from bronze once per run
(`_bronze_submissions_lookup`; hits cached, misses re-checked).
`PARSER_VERSION` 2 → 3.

| Item | Delivered |
|---|---|
| 1 | `other_text` per owner; `filing_footnote_text` and `filing_remarks` — document-level in the SEC schema (0 `footnoteId` inside `reportingOwnerRelationship` across 5,356 filings), so duplicated onto each owner row and named as filing-level |
| 2 | `owner_submissions_present`, `owner_submissions_sha256` (which bronze snapshot), and the seven structural fields `owner_entity_type`, `owner_sic`, `owner_state_of_incorporation`, `owner_ein`, `owner_ticker_count`, `owner_org`, `owner_fiscal_year_end`; plus `owner_name_raw`, the registry form rule C-J and the normalizer read. **Zero SEC requests.** The classifier itself stays in the MDM consumer |
| 3 | `address_is_care_of` (street1 begins `C/O`) and `address_non_us`; no street, city, state or zip leaves the parser (key-name test) |
| 4 | **Restated — see below.** `reporting_owner_count` and `ownership_nature` on both transaction tables; gold `ownership_holdings` / `ownership_activity` no longer attribute joint-filing transactions to owner 1 |

**Item 4's premise did not hold.** The SEC Ownership XML schema's
`NONDERIVATIVE_TRANSACTION` / `DERIVATIVE_TRANSACTION` types carry no owner
reference of any kind; the 119 joint filings in research 18's corpus
attribute only in free-text `natureOfOwnership` ("By DST Global VI, L.P.",
"See footnote"). There is no "real `owner_index`" to emit. Transaction rows
keep `owner_index = 1` — the landing key, exact on single-owner filings —
and carry `reporting_owner_count` so every consumer fails closed. Fan-out
(one row per owner per transaction) was rejected: it would put a fund's
indirect position under a natural person's name and multiply gold share
totals by the owner count. `docs/specs/person/consumer.md` holdings
paragraph, gate 8 and the dependencies row are amended accordingly. In
research 18's corpus the change stops misattributing **486 of 10,964
transaction rows (4.43%) on 110 filings**.

**Evidence, zero network** (`research/19-*`):
- **Equivalence**, 5,356 bronze artifacts, old parser (edgartools' `Entity`
  fed the same bronze snapshot through its own `parse_entity_submissions`)
  vs new: identical row counts (5,741 owners / 8,172 / 2,785 transactions);
  new parser 0 errors, old 2; `owner_name` identical on every owner. Every
  difference is the old path losing data: `&` and `"` dropped by its
  BeautifulSoup route (550 titles, 58 security titles, 14 names), NaN where
  a value was absent (now NULL), `underlying_security_title` empty on all
  2,785 derivative rows (read the wrong attribute), and 202 footnoted
  numerics `_to_float` had dropped.
- **Rule C-J from parser columns alone** reproduces research 18's frozen
  labelled corpus exactly: **841/841 person, 353/353 entity, 26 deferred**
  (5,743 rows, 4,831 owners), 0 SEC requests; 119/119 joint filings marked.

**Deploy order**: `20_silver_landing_ownership_evidence.sql` (now in
`install.sh`'s silver-landing stage) → image rollout → next ownership
artifact run re-parses (no `--force`) → `dbt run --select
sec_ownership_reporting_owner sec_ownership_non_derivative_txn
sec_ownership_derivative_txn ownership_holdings ownership_activity
--full-refresh`.

**Watch after the first re-parse**: the `owner_submissions_present = false`
rate. Research 18 found a bronze snapshot for 4,831/4,831 owner CIKs, but
nothing guarantees owner-CIK capture ahead of the parse. A missing snapshot
defers classification **and** reverses an entity owner's `owner_name`, and
does not heal until the next version bump or forced re-parse.

**Review** (three axes): Standards — no blocking; should-fix: wire migration
20 into `install.sh`, per-run lookup lifetime, required `submissions_lookup`
on the parse pipeline, six stale docs naming `Ownership.from_xml`, test gaps
(call sites, each `_is_company` signal incl. the 50-form slice, malformed
transaction) — all done. Spec — blocking: spec and ticket still required an
impossible `owner_index` fix — amended (this section; consumer.md); should-
fix: gold still attributed joint filings (fixed), no snapshot provenance
(`owner_submissions_sha256`), coverage unmeasured (recorded above), item 1
wording (restated). GoF — one finding, the lookup cache rebuilt per filing
(fixed, lifetime pinned by test); the family-dispatch conditional and the
dict-shaped evidence left as they are.

## Question

Nothing to decide. Graduated from the map's fog by ticket 04, which fixed
the field set and so fixed what the parser must keep. Three changes to
`edgar_warehouse/parsers/ownership.py` and its silver columns, all in the
same area, for whoever owns `edgar_warehouse/parsers/`:

1. **Keep `otherText` (per owner) and the filing's footnotes and remarks**
   (document-level in the SEC schema — no `footnoteId` occurs inside
   `reportingOwnerRelationship` — duplicated onto each owner row as
   `filing_footnote_text`, `filing_remarks`). *Originally: "per-owner
   footnote text".* Ticket 03's rule C-J
   treats deputization language as evidence; research 18 read it from
   bronze because silver does not carry it. Today
   `sec_ownership_reporting_owner` has `is_other` but not its text
   (`edgar_warehouse/silver_schema.py:422-435`).
2. **Classify from the bronze `submissions.json`, not a live SEC fetch.**
   `Ownership.from_xml` fetches every reporting owner's submissions live at
   parse time (edgartools 5.30.0 `ownershipforms.py:1017-1020`) and computes
   an `is_company` the repo discards. Rule C-J needs `entityType`, `sic`,
   `stateOfIncorporation`, `ein`, `tickers`, `ownerOrg`, `fiscalYearEnd`
   for each owner CIK — all present in bronze for 4,831/4,831 owner CIKs
   measured (research 18). Feed bronze; make zero SEC requests.
3. **Reduce the owner address to two booleans and drop the rest.** Ticket 04
   Q4: no street/city/state/zip may enter silver, an assertion, or a
   projection. Keep only `address_is_care_of` and `address_non_us` as
   classification evidence; bronze retains the raw artifact unchanged.
4. **Mark joint-filing transactions; the SEC schema has no per-transaction
   owner.** *Originally: "Emit the real `owner_index` on transaction rows."* Added by ticket 05.
   Every transaction row hardcodes `"owner_index": 1`
   (`edgar_warehouse/parsers/ownership.py:47`, `:66`), so on a multi-owner
   Form 4 all transactions join to reporting owner 1 (`pipeline.py:1979-1980`;
   `ownership_holdings.sql:38-39`) — one owner's positions attributed to
   another named person. This is a release gate for publishing any Person
   holdings edge, alongside the Security identity gate.

Production parser code: its own branch, the mandatory
`/gof-refactor-reviewer` consult, the three-axis `/code-review`. Note
research 12 F8 — the per-filing fetch has no `--force`, so a parser change
alone does not re-parse already-marked accessions. Sibling of
[ticket 10](10-fix-proxy-executive-name-parser-leak.md); the two touch
different parsers and can land independently.

Resolved when the four fields/behaviours are present in a re-exported
silver sample, rule C-J can be evaluated without any SEC request, and every
transaction on a multi-owner Form 4 carries `reporting_owner_count > 1` and
its `ownership_nature` text, so no consumer can attribute it to one owner by
joining on `owner_index`. *Originally: "a multi-owner Form 4 shows each
owner's own transactions" — not representable; see Resolution.*
