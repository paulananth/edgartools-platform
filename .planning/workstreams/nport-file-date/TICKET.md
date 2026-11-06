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
- [ ] Replay the retained local scope through normal controlled callers;
  verify actual relationship and quality counts plus zero-work repeat.
- [ ] Reflect the qualified link and provisional-date defect in OpenMetadata;
  require native readback and preserve unrelated metadata.
- [x] Review Standards, Spec and GoF: no implementation findings. Historical
  issue 30 answer labeled superseded (2026-11-06 06:52 ET).
- [ ] Publish and verify the final PR head; record source approvals in Git
  against that PR's reference (effective on merge). Live activation used
  captured-data proof, independently of the finalized-on-main shortcut.
- [x] Learning → skill: data-quality's Approved provisional dates, ready
  PR #1450, documents observed validity with an open authoritative-start defect
  (2026-11-06 06:52 ET).

## Design consult: GoF

The available gof-refactor-reviewer was read with adapter and relationship
history. The existing engine already supplies an observed start from the
source effective time and validates endpoint profiles. Reuse that mechanism
through configuration, rather than adding date or source branches to code.
No pattern refactor is justified.
