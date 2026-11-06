# Provisional filing dates for N-PORT fund relationships

Operator ruling, 2026-11-06: "make it valid with the file date until we fix
the data quality reflect this in open metadata". This supersedes the earlier
"Funds now, link later" deferral for the verified series/registrant association.
The file date is SUBMISSION.FILING_DATE, a reported calendar date. The true
relationship/registration inception remains unknown.

- [x] Configure observed filing-date starts, required endpoint fund profiles,
  and nonblocking quality flags; captured-scope comparison preserves keys and
  identity fields (2026-11-06 06:52 ET).
- [x] Prove reading/normalization/relationship behavior: 25 invented date,
  endpoint and relationship-history tests plus 149 affected tests pass; old
  mapping fails because effective_at is None rather than the filing date
  (2026-11-06 07:00 ET; added registrant first/latest invalid-date cases).
- [x] Measure retained scope: 12,937 projected links, 1,245 resolved targets,
  zero reviews; seven unchanged invalid-LEI exclusions. Both regenerated
  Mapping Documents pass their checks (2026-11-06 06:52 ET).
- [x] Save, prove, approve and activate both provisional-file-date source
  versions through normal Rules callers, using captured-data proof and the
  operator's exact words (2026-11-06 06:52 ET).
- [x] Both controlled replays complete (2.6 and 43.3 minutes). Governed
  readback confirms 12,937 observed-date links to 1,245 targets, 12,937 series
  flags and 1,947 registrant flags. All identity fields unchanged; normal
  repeat selects zero new documents for both sources (2026-11-06 07:30 ET).
- [x] Native OpenMetadata 2.0.2 readback confirms the typed relationship,
  five qualified descriptions and both measured quality results. No Shared
  domain/glossary; unrelated metadata preserved (2026-11-06 07:30 ET).
- [x] Review Standards, Spec and GoF: no implementation findings. Historical
  issue 30 answer labeled superseded (2026-11-06 06:52 ET).
- [x] Publish ready PR #1454 and record both exact source approvals in Git
  against that PR (effective on merge). All current rules have listed approval;
  seven approval tests pass, and the rebased source/date/history/approval suite
  passes 32 tests (2026-11-06 07:34 ET). CI/merge are recorded on the PR.
  Live activation used captured-data proof, independently of the
  finalized-on-main shortcut.
- [x] Learning → skill: data-quality's Approved provisional dates, merged
  PR #1450, documents observed validity with an open authoritative-start defect
  (2026-11-06 06:52 ET).

## Design consult: GoF

The available gof-refactor-reviewer was read with adapter and relationship
history. The existing engine already supplies an observed start from the
source effective time and validates endpoint profiles. Reuse that mechanism
through configuration, rather than adding date or source branches to code.
No pattern refactor is justified.

## Standards

Configuration and invented tests only; no production code change. Source
identities remain unchanged. Both Mapping Documents regenerated and checked;
25 date/history, 149 affected and 98 genericity/path checks pass. The old mapping
fails the filing-observation assertion. Exact captured-data approval was used
before activation; no finalized-on-main shortcut was used on unmerged rules.

## Spec

The operator-approved filing date now makes the real mastered relationship
valid. Its observed basis and nonblocking flag keep the unknown true inception
visible. Both endpoint registrations cover the interval. Actual mastered
readback, zero-work repeat and OpenMetadata readback confirm the outcome.

## GoF

Independent review recommends keeping the existing design. Reuse the tested
source normalization, endpoint registration and observed-period history seams.
Malformed source observations fail normalization; malformed registration
observations fail the relationship interval check.
