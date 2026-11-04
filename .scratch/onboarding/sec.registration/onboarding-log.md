# Onboarding log: SEC registration statements (ticket 149)

## Rulings (operator, 2026-10-29)

- "complete 149 authotised to download S-1": SEC requests for the S-1 feed are authorised.
- Scope: "S-1 + F-1 originals, main doc (Recommended)": 9,646 filings (7,849 S-1, 1,797 F-1) listed in the
  captured submissions; the registration statement document only.
- Output: "IPO pipeline + offering terms (Recommended)".
- Capture: "Extend the configured capture (Recommended)".

## The source

- The filings index is already captured: each filer's submissions document lists form, accession, filing date,
  primary document name and size (`sec.submissions.company`, capture `all-76230`).
- The document's address is the filing's folder in the SEC archive plus its primary document name.
- `EFFECT` (effectiveness) and `424B4` (final prospectus) dates are in the same index: no download needed for
  the pipeline's dates.

## Gaps found

- The configured capture (`provider.capture`) accepts JSON payloads only (`completeness.format` json or
  json_array); an S-1 main document is HTML. Code change approved (above).
- `EDGAR_IDENTITY` is not set in the agent's environment; the operator sets it.

## Capture (2026-10-29)

- Units from the submissions index: 9,538 of 9,646 filings (78 with no electronic document, 30 repeated
  co-registrant listings). The index's `size` is the whole filing (exhibits too: 89.7 GB in all), not the
  main document, so the feed's bound is the transport's 128 MiB ceiling.
- Main documents by extension: `.htm` 9,454, `.txt` 114, `.paper` 3, none 75.
- Gap: the configured capture cannot run before its own acquisition proof exists, and no source has made
  one yet (SEC Company, GLEIF and OpenFIGI moved theirs to ticket 71). The proof here is 5 documents through
  the capture's transport, each kept with its receipt and read back.
- Proof: 5 asked, 5 kept, 5 verified; 0.66 to 1.44 MB each.

## The capture run (2026-10-29, explored on company-on)

- Switched on on the operator's words "Switch on and download (Recommended)" (22:02 ET): version
  `sec.registration-2026-10-29.first-capture`, proven by the 5-document proof, approved, active.
- One run of all 9,538 units: each claim re-checks the whole frozen run, about 4 minutes a unit
  (`Bookkeeping._frozen` reads every unit and stored row on each call). Left open with 2 verified.
- Its files cannot be reused by another run ("Capture snapshot differs from frozen work"): a snapshot
  belongs to the run that made it, so the bundles of 100 write to their own folder.
- Bundles of 100: each worker call captures one document only. A reported unit holds the shared
  `provider:sec` lease until its verifier admits it (lease 300 s), so the next claim finds nothing until
  then: about 12 s a document, about 32 hours for 9,538. A fix is code (Bookkeeping), so it is asked first.
- Format inventory for discover: `.htm` 9,454, `.txt` 114. The configured engine reads JSON, CSV/TSV,
  XML, SGML-wrapped XML and Parquet; no HTML reader, so profiling and the source extract of the
  offering terms need one (a code ticket, asked first). The IPO pipeline's dates are in the submissions
  JSON, which the engine reads today.

## Questions and answers (2026-10-30)

- Q: from 2022 about half the main documents hold no fee table (193 of 384); take offering terms from the
  main document only, or also request each filing's fee exhibit? A: "Main doc only (Recommended)".
- Gap: the profiler reads JSON Lines, CSV, Parquet, JSON and XML, not HTML. Profiling reads the configured
  HTML reading's output (blocks and rows as JSON Lines), not the pages.
- A document the SEC refuses stalls its Bookkeeping run (no unit is ever given up): set aside after 3
  attempts, the rest of its bundle in a new run.
