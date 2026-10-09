# DTCC enrichment

Owner: Codex. Status: open. Started: 2026-10-09.

## Scope and evidence

Evaluate DTCC sources for Company MDM and SEC enrichment. Security Position
Reports and selected CUSIP restriction/certification lists remain in scope at
lower priority, per operator instruction. Purchases, subscriptions, production
changes and automatic identity bindings require their own decisions.

Research and access findings: [DTCC public data](../../../docs/research/dtcc-public-data-2026-10-09.md).
Keep source participant accounts distinct from Company identity. Record directory
publication dates separately from membership effective dates. Name matches are
candidates until reviewed evidence supports a binding.

## Check-in and review

- [x] Save sourced research and the operator-approved checklist; relative links and scope checked, git diff --check passed (2026-10-09 16:41 ET).
- [ ] Commit on the dedicated Codex branch after the overlap guard passes.
- [ ] Push and create a ready PR after the overlap guard passes.

## Priority 1: Company enrichment

Discovery follows data-onboarding and data-profiling. See the
[onboarding log](../../../.scratch/onboarding/dtcc-directories/onboarding-log.md).
Findings remain unapproved until the operator reviews them.

- [ ] Exercise the profiling skill on pinned local inputs; preserve original-versus-derived input lineage.
- [ ] Refine skills only for demonstrated gaps, respecting ownership; verify documentation links and affected checks.

- [ ] Inventory DTC, NSCC and FICC participant directories and settling-bank lists; record current URLs and formats.
- [ ] Verify anonymous download access and documented update frequency; record file versus landing-page dates.
- [ ] Establish permitted automation, internal use and redistribution rights; public access alone is insufficient.
- [ ] Capture dated public files with checksums, byte counts and source provenance; keep raw data outside Git.
- [ ] Profile identifiers, names, duplicate accounts, workbook layout and membership roles; report exact sample coverage.
- [ ] Measure overlap with our pinned SEC/GLEIF Company population; distinguish candidate names from verified identity matches.
- [ ] Define reviewed matching rules and account-to-Company cardinality; retain unresolved candidates.
- [ ] Qualify configuration-driven reading and Company enrichment against captured fixtures and independent expectations.
- [ ] Evaluate membership notices/RSS for changes and effective dates; identify selective coverage and backfill limits.

## Priority 2: selected CUSIP restriction/certification lists

- [ ] Inventory public restriction, ownership-certification and special-deposit lists.
- [ ] Verify CUSIP usage rights, document dates and coverage limitations.
- [ ] Profile CUSIPs, descriptions and restriction types.
- [ ] Measure overlap with SEC holdings and existing security identifiers.
- [ ] Qualify extraction against captured documents.
- [ ] Define dated security-level observations and verified issuer links.

## Priority 3: Security Position Reports

- [ ] Confirm eligibility as an issuer, trustee or approved third-party agent.
- [ ] Establish permitted coverage, registration requirements and licensing terms.
- [ ] Obtain pricing for subscriptions and individual reports.
- [ ] Obtain an authorized sample and profile its fields.
- [ ] Distinguish DTC participant positions from ultimate beneficial ownership.
- [ ] Assess useful reconciliation with SEC holdings disclosures.
- [ ] Qualify ingestion after access and use rights are established.

## Acceptance and decision

- [ ] Report measured coverage, matching accuracy, maintenance effort and cost per source.
- [ ] Preserve source identifiers, dates and evidence for every enrichment.
- [ ] Verify ambiguous names cannot create automatic Company bindings.
- [ ] Verify participant positions cannot become unsupported beneficial-ownership claims.
- [ ] Select sources for implementation based on demonstrated value.
