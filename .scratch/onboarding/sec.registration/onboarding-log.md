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
