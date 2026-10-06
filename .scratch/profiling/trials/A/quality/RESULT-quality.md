# Quality trial

Trial A: profiled with the current code; findings approved for this trial only.

| Part | Defects | Became checks or fixes | Counts equal | Planted fire | New code |
|---|---|---|---|---|---|
| submissions.filings.recent | 8 | 7 | 7 of 7 | 7 of 7 | hierarchy_invalid |
| submissions.formerNames | 1 | 0 | 0 of 0 | 0 of 0 | no_natural_key |
| submissions.tickers | 1 | 0 | 0 of 0 | 0 of 0 | link_not_found |
| submissions.exchanges | 2 | 1 | 1 of 1 | 1 of 1 | no_natural_key |
| submissions | 28 | 21 | 21 of 21 | 21 of 21 | hierarchy_invalid |
| tickers | 3 | 2 | 2 of 2 | 2 of 2 | link_not_found |
| lei2.Entity.LegalEntityEvents.LegalEntityEvent.AffectedFields.AffectedField | 1 | 0 | 0 of 0 | 0 of 0 | no_natural_key |
| lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress.AdditionalAddressLine | 1 | 0 | 0 of 0 | 0 of 0 | no_natural_key |
| lei2.Entity.OtherAddresses.OtherAddress.AdditionalAddressLine | 1 | 0 | 0 of 0 | 0 of 0 | no_natural_key |
| lei2.Entity.LegalAddress.AdditionalAddressLine | 1 | 0 | 0 of 0 | 0 of 0 | no_natural_key |
| lei2.Entity.HeadquartersAddress.AdditionalAddressLine | 1 | 0 | 0 of 0 | 0 of 0 | no_natural_key |
| lei2.Entity.OtherEntityNames.OtherEntityName | 1 | 0 | 0 of 0 | 0 of 0 | no_natural_key |
| lei2.Entity.LegalEntityEvents.LegalEntityEvent | 5 | 4 | 4 of 4 | 4 of 4 | no_natural_key |
| lei2.Registration.OtherValidationAuthorities.OtherValidationAuthority | 2 | 1 | 1 of 1 | 1 of 1 | no_natural_key |
| lei2.Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName | 1 | 0 | 0 of 0 | 0 of 0 | no_natural_key |
| lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress | 2 | 2 | 2 of 2 | 2 of 2 | - |
| lei2.Entity.OtherAddresses.OtherAddress | 3 | 3 | 3 of 3 | 3 of 3 | - |
| lei2.Extension.gleif:Geocoding | 9 | 7 | 7 of 7 | 7 of 7 | hierarchy_invalid, no_natural_key |
| lei2.Entity.SuccessorEntity | 1 | 0 | 0 of 0 | 0 of 0 | no_natural_key |
| lei2 | 31 | 23 | 23 of 23 | 23 of 23 | hierarchy_invalid |
| rr.RelationshipRecord.Relationship.RelationshipPeriods.RelationshipPeriod | 2 | 1 | 1 of 1 | 1 of 1 | no_natural_key |
| rr.RelationshipRecord.Relationship.RelationshipQualifiers.RelationshipQualifier | 2 | 1 | 1 of 1 | 1 of 1 | no_natural_key |
| rr.RelationshipRecord.Relationship.RelationshipQuantifiers.RelationshipQuantifier | 1 | 1 | 1 of 1 | 1 of 1 | - |
| rr | 17 | 7 | 7 of 7 | 7 of 7 | hierarchy_invalid, link_not_found |
| repex.ExceptionReason | 2 | 1 | 1 of 1 | 1 of 1 | no_natural_key |
| repex.ExceptionReference | 1 | 0 | 0 of 0 | 0 of 0 | no_natural_key |

82 of 128 defects became engine checks or fixes; the rest are new code, each with what its check would test (QUALITY.md per part). A code-list guard counts 0 on its own delivery by design: its planted record proves it fires.

Invalid hierarchy rows marked: 7170; 3903 with an evidence-backed fix, 3267 for a steward; 0 without either.

**Every check loads, counts what profiling counted, and fires.**

## Reading this result

- Run time: 54 minutes (profile, then every part's records measured with the engine's checks), 2026-10-05
  21:29 to 22:23 ET. The profile still scores 38 of 41 on the answer key (the same three key items as
  before, explained in [../RESULT.md](../RESULT.md)).
- The 3,192 "names itself as its parent" rows are funds whose manager is themselves, and 22 rows are on a
  two-node cycle; both go to a steward, with no fix.
- Several functional-dependency hierarchies here are coincidences between codes, not hierarchies (a flag
  over the form type, an address country over a legal jurisdiction). Their fixes ("the parent most rows
  with the code have") are proposals a steward approves or rejects, never applied by themselves. Telling
  such coincidences from real hierarchies is a profiling follow-up, logged on ticket 01c.
- `invalid_rows.summary.md` counts every marked row by hierarchy and reason.
