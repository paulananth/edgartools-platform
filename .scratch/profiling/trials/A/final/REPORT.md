# Profiling report: None

Profiled 2026-10-05T19:51:14-04:00 by data-profiling 1. Scan: **sampled** (an input over 5 GB, seed 0); 3368.6 s. Approval: **draft**.

## Parts

| Part | Rows | Class | Confidence | Record key | Store (advice) |
|---|---|---|---|---|---|
| submissions.filings.recent | 8065661 | transaction | 0.833 | cik, accessionNumber | silver |
| submissions.filings.files | 3984 | transaction | 1.0 | name | silver |
| submissions.formerNames | 14268 | master | 0.833 | cik, _position (designed: natural_composite) | mdm |
| submissions.tickers | 9528 | master | 0.833 | cik, value | mdm |
| submissions.exchanges | 9528 | master | 0.833 | cik, _position (designed: natural_composite) | mdm |
| submissions | 76230 | master | 0.833 | cik | mdm |
| tickers | 10391 | master | 0.833 | ticker | mdm |
| lei2.Entity.LegalEntityEvents.LegalEntityEvent.AffectedFields.AffectedField | 1379 | master | 1.0 | LEI, _position, _position (designed: natural_composite) | mdm |
| lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress.AdditionalAddressLine | 1988 | master | 1.0 | LEI, @type, _position (designed: natural_composite) | mdm |
| lei2.Entity.OtherAddresses.OtherAddress.AdditionalAddressLine | 683 | master | 1.0 | LEI, @type, _position (designed: natural_composite) | mdm |
| lei2.Entity.LegalAddress.AdditionalAddressLine | 43223 | master | 1.0 | LEI, _position (designed: natural_composite) | mdm |
| lei2.Entity.HeadquartersAddress.AdditionalAddressLine | 38356 | master | 1.0 | LEI, _position (designed: natural_composite) | mdm |
| lei2.Entity.OtherEntityNames.OtherEntityName | 14120 | master | 1.0 | LEI, _position (designed: natural_composite) | mdm |
| lei2.Entity.LegalEntityEvents.LegalEntityEvent | 36881 | master | 1.0 | LEI, _position (designed: natural_composite) | mdm |
| lei2.Registration.OtherValidationAuthorities.OtherValidationAuthority | 9234 | master | 1.0 | LEI, _position (designed: natural_composite) | mdm |
| lei2.Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName | 4664 | master | 1.0 | LEI, _position (designed: natural_composite) | mdm |
| lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress | 4865 | master | 1.0 | LEI, @type | mdm |
| lei2.Entity.OtherAddresses.OtherAddress | 2518 | master | 1.0 | LEI, @type | mdm |
| lei2.Extension.gleif:Geocoding | 50787 | master | 1.0 | LEI, _position (designed: natural_composite) | mdm |
| lei2.Entity.SuccessorEntity | 1548 | master | 1.0 | LEI, _position (designed: natural_composite) | mdm |
| lei2 | 100000 | master | 1.0 | LEI | mdm |
| rr.RelationshipRecord.Relationship.RelationshipPeriods.RelationshipPeriod | 859473 | relationship | 1.0 | RelationshipRecord.Relationship.StartNode.NodeID, RelationshipRecord.Relationship.RelationshipType, _position (designed: natural_composite) | mdm_relationships |
| rr.RelationshipRecord.Relationship.RelationshipQualifiers.RelationshipQualifier | 151970 | relationship | 1.0 | RelationshipRecord.Relationship.StartNode.NodeID, RelationshipRecord.Relationship.RelationshipType, _position (designed: natural_composite) | mdm_relationships |
| rr.RelationshipRecord.Relationship.RelationshipQuantifiers.RelationshipQuantifier | 52157 | transaction | 0.833 | RelationshipRecord.Relationship.StartNode.NodeID, RelationshipRecord.Relationship.RelationshipType, QuantifierAmount | silver |
| rr | 487721 | relationship | 1.0 | RelationshipRecord.Relationship.StartNode.NodeID, RelationshipRecord.Relationship.RelationshipType | mdm_relationships |
| repex.ExceptionReason | 6365847 | transaction | 0.833 | LEI, ExceptionCategory, _position (designed: natural_composite) | silver |
| repex.ExceptionReference | 2951 | transaction | 0.833 | LEI, ExceptionCategory, _position (designed: natural_composite) | silver |
| repex | 6351397 | transaction | 0.833 | LEI, ExceptionCategory | silver |

## Why each class

- **submissions.filings.recent** is transaction: has a unique key (required); points at other parts; points at as many parts as point at it; has an event time or measures; at least as large as the parts it points at. Failed: no name-like text.
- **submissions.filings.files** is transaction: has a unique key (required); points at other parts; points at as many parts as point at it; has an event time or measures; no name-like text; at least as large as the parts it points at.
- **submissions.formerNames** is master: a list inside its parent's records, with no key of its own.
- **submissions.tickers** is master: a list inside its parent's records, with no key of its own.
- **submissions.exchanges** is master: a list inside its parent's records, with no key of its own.
- **submissions** is master: has a unique key (required); other parts point at it; points at few parts; has name-like text; has attributes besides codes and dates. Failed: smaller than the parts pointing at it.
- **tickers** is master: has a unique key (required); other parts point at it; points at few parts; has name-like text; has attributes besides codes and dates. Failed: smaller than the parts pointing at it.
- **lei2.Entity.LegalEntityEvents.LegalEntityEvent.AffectedFields.AffectedField** is master: a list inside its parent's records, with no key of its own.
- **lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress.AdditionalAddressLine** is master: a list inside its parent's records, with no key of its own.
- **lei2.Entity.OtherAddresses.OtherAddress.AdditionalAddressLine** is master: a list inside its parent's records, with no key of its own.
- **lei2.Entity.LegalAddress.AdditionalAddressLine** is master: a list inside its parent's records, with no key of its own.
- **lei2.Entity.HeadquartersAddress.AdditionalAddressLine** is master: a list inside its parent's records, with no key of its own.
- **lei2.Entity.OtherEntityNames.OtherEntityName** is master: a list inside its parent's records, with no key of its own.
- **lei2.Entity.LegalEntityEvents.LegalEntityEvent** is master: a list inside its parent's records, with no key of its own.
- **lei2.Registration.OtherValidationAuthorities.OtherValidationAuthority** is master: a list inside its parent's records, with no key of its own.
- **lei2.Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName** is master: a list inside its parent's records, with no key of its own.
- **lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress** is master: a list inside its parent's records, with no key of its own.
- **lei2.Entity.OtherAddresses.OtherAddress** is master: a list inside its parent's records, with no key of its own.
- **lei2.Extension.gleif:Geocoding** is master: a list inside its parent's records, with no key of its own.
- **lei2.Entity.SuccessorEntity** is master: a list inside its parent's records, with no key of its own.
- **lei2** is master: has a unique key (required); other parts point at it; points at few parts; has name-like text; smaller than the parts pointing at it; has attributes besides codes and dates.
- **rr.RelationshipRecord.Relationship.RelationshipPeriods.RelationshipPeriod** is relationship: a list inside its parent's records, with no key of its own.
- **rr.RelationshipRecord.Relationship.RelationshipQualifiers.RelationshipQualifier** is relationship: a list inside its parent's records, with no key of its own.
- **rr.RelationshipRecord.Relationship.RelationshipQuantifiers.RelationshipQuantifier** is transaction: has a unique key (required); points at other parts; points at as many parts as point at it; no name-like text; at least as large as the parts it points at. Failed: has an event time or measures.
- **rr** is relationship: key made of links to other parts (required); points at two or more parts; nothing points at it; few attributes besides codes and dates.
- **repex.ExceptionReason** is transaction: a list inside its parent's records, with no key of its own.
- **repex.ExceptionReference** is transaction: a list inside its parent's records, with no key of its own.
- **repex** is transaction: has a unique key (required); points at other parts; points at as many parts as point at it; no name-like text; at least as large as the parts it points at. Failed: has an event time or measures.

## Relationships

| From | To | Inclusion | Cardinality | Onboard | Why |
|---|---|---|---|---|---|
| lei2.Entity.SuccessorEntity.SuccessorLEI | lei2.LEI | 1.0 | N:1 | together | an attribute list of its master |
| repex.LEI | lei2.LEI | 1.0 | N:1 | separate | a transaction part pointing at a master part: onboarded after it |
| rr.RelationshipRecord.Relationship.EndNode.NodeID | lei2.LEI | 0.999936 | N:1 | together | a link between masters, mastered with them |
| rr.RelationshipRecord.Relationship.StartNode.NodeID | lei2.LEI | 1.0 | N:1 | together | a link between masters, mastered with them |
| submissions.tickers.value | tickers.ticker | 0.951721 | 1:1 | separate | a master part pointing at a master part: onboarded after it |
| tickers.cik | submissions.cik | 0.908011 | N:1 | separate | a master part pointing at a master part: onboarded after it |
| lei2.Entity.HeadquartersAddress.AdditionalAddressLine._parent_row | lei2._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Entity.LegalAddress.AdditionalAddressLine._parent_row | lei2._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Entity.LegalEntityEvents.LegalEntityEvent._parent_row | lei2._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Entity.LegalEntityEvents.LegalEntityEvent.AffectedFields.AffectedField._parent_row | lei2.Entity.LegalEntityEvents.LegalEntityEvent._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Entity.OtherAddresses.OtherAddress._parent_row | lei2._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Entity.OtherAddresses.OtherAddress.AdditionalAddressLine._parent_row | lei2.Entity.OtherAddresses.OtherAddress._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Entity.OtherEntityNames.OtherEntityName._parent_row | lei2._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Entity.SuccessorEntity._parent_row | lei2._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress._parent_row | lei2._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress.AdditionalAddressLine._parent_row | lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName._parent_row | lei2._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Extension.gleif:Geocoding._parent_row | lei2._row | 1.0 | N:1 | together | an attribute list of its master |
| lei2.Registration.OtherValidationAuthorities.OtherValidationAuthority._parent_row | lei2._row | 1.0 | N:1 | together | an attribute list of its master |
| repex.ExceptionReason._parent_row | repex._row | 1.0 | N:1 | separate | a transaction part pointing at a transaction part: onboarded after it |
| repex.ExceptionReference._parent_row | repex._row | 1.0 | N:1 | separate | a transaction part pointing at a transaction part: onboarded after it |
| rr.RelationshipRecord.Relationship.RelationshipPeriods.RelationshipPeriod._parent_row | rr._row | 1.0 | N:1 | separate | a link between masters, mastered with them |
| rr.RelationshipRecord.Relationship.RelationshipQualifiers.RelationshipQualifier._parent_row | rr._row | 1.0 | N:1 | separate | a link between masters, mastered with them |
| rr.RelationshipRecord.Relationship.RelationshipQuantifiers.RelationshipQuantifier._parent_row | rr._row | 1.0 | N:1 | separate | a transaction part pointing at a relationship part: onboarded after it |
| submissions.exchanges._parent_row | submissions._row | 1.0 | N:1 | together | an attribute list of its master |
| submissions.filings.files._parent_row | submissions._row | 1.0 | N:1 | separate | a transaction part pointing at a master part: onboarded after it |
| submissions.filings.recent._parent_row | submissions._row | 1.0 | N:1 | separate | a transaction part pointing at a master part: onboarded after it |
| submissions.formerNames._parent_row | submissions._row | 1.0 | N:1 | together | an attribute list of its master |
| submissions.tickers._parent_row | submissions._row | 1.0 | N:1 | together | an attribute list of its master |

## Hierarchies

- **submissions.filings.recent: isXBRLNumeric > form** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.997196, depth 2, balanced, orphans 0, cycles 0, invalid rows 22616.
- **submissions: flags > ownerOrg > sicDescription > sic** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.996102, depth 4, balanced, orphans 0, cycles 0, invalid rows 297.
- **submissions: flags > fiscalYearEnd** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.999689, depth 2, balanced, orphans 0, cycles 0, invalid rows 24.
- **submissions: flags > stateOfIncorporation** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.999843, depth 2, balanced, orphans 0, cycles 0, invalid rows 12.
- **submissions: addresses.mailing.isForeignLocation > addresses.mailing.stateOrCountry** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.99993, depth 2, balanced, orphans 0, cycles 0, invalid rows 5.
- **submissions: flags > addresses.business.stateOrCountry** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.999704, depth 2, balanced, orphans 0, cycles 0, invalid rows 23.
- **submissions: addresses.mailing.isForeignLocation > addresses.mailing.country > addresses.mailing.countryCode** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 1.0, depth 3, balanced, orphans 0, cycles 0, invalid rows 0.
- **submissions: flags > addresses.business.country** (reference, code_nesting): each code starts with its parent's code; holds 1.0, depth 2, balanced, orphans 0, cycles 0, invalid rows 0.
- **submissions: flags > category** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.999829, depth 2, balanced, orphans 0, cycles 0, invalid rows 13.
- **submissions: flags > entityType** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.999829, depth 2, balanced, orphans 0, cycles 0, invalid rows 13.
- **lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress: Country > Region** (reference, code_nesting): each code starts with its parent's code; holds 1.0, depth 2, balanced, orphans 0, cycles 0, invalid rows 0.
- **lei2.Entity.OtherAddresses.OtherAddress: AddressNumberWithinBuilding > Country** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 1.0, depth 2, balanced, orphans 0, cycles 0, invalid rows 0.
- **lei2.Entity.OtherAddresses.OtherAddress: AddressNumberWithinBuilding > @xml:lang** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 1.0, depth 2, balanced, orphans 0, cycles 0, invalid rows 0.
- **lei2.Extension.gleif:Geocoding: gleif:match_level > gleif:geocoding_failed > gleif:mapped_country > gleif:mapped_state** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.992594, depth 4, balanced, orphans 0, cycles 0, invalid rows 376.
- **lei2: Entity.LegalAddress.Country > Entity.LegalAddress.Region** (reference, code_nesting): each code starts with its parent's code; holds 0.999985, depth 2, balanced, orphans 0, cycles 0, invalid rows 1.
- **lei2: Entity.HeadquartersAddress.Country > Entity.HeadquartersAddress.Region** (reference, code_nesting): each code starts with its parent's code; holds 0.999971, depth 2, balanced, orphans 0, cycles 0, invalid rows 3.
- **lei2: Entity.EntityCategory > Extension.leifr:LegalFormCodification > Entity.LegalForm.EntityLegalFormCode** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.999492, depth 3, balanced, orphans 0, cycles 0, invalid rows 51.
- **lei2: Entity.RegistrationAuthority.RegistrationAuthorityID > Registration.ValidationAuthority.ValidationAuthorityID** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.99536, depth 2, balanced, orphans 0, cycles 0, invalid rows 464.
- **lei2: Entity.LegalAddress.Country > Entity.LegalJurisdiction** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.99795, depth 2, balanced, orphans 0, cycles 0, invalid rows 205.
- **lei2: Entity.LegalAddress.@xml:lang > Entity.HeadquartersAddress.@xml:lang** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.996386, depth 2, balanced, orphans 0, cycles 0, invalid rows 361.
- **lei2: Entity.EntityStatus > Registration.RegistrationStatus** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.99978, depth 2, balanced, orphans 0, cycles 0, invalid rows 22.
- **lei2: Entity.EntityStatus > Entity.EntitySubCategory** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.99422, depth 2, balanced, orphans 0, cycles 0, invalid rows 578.
- **rr: RelationshipRecord.Relationship.RelationshipStatus > RelationshipRecord.Registration.ManagingLOU** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.99917, depth 2, balanced, orphans 0, cycles 0, invalid rows 405.
- **rr: RelationshipRecord.Relationship.RelationshipStatus > RelationshipRecord.Registration.ValidationDocuments** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.99917, depth 2, balanced, orphans 0, cycles 0, invalid rows 405.
- **rr: RelationshipRecord.Relationship.RelationshipStatus > RelationshipRecord.Registration.RegistrationStatus** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.99917, depth 2, balanced, orphans 0, cycles 0, invalid rows 405.
- **rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_DIRECTLY_CONSOLIDATED_BY)** (master_data, parent_column): RelationshipRecord.Relationship.StartNode.NodeID has one RelationshipRecord.Relationship.EndNode.NodeID per role; holds 1.0, depth 10, ragged, orphans 0, cycles 8, invalid rows 8.
- **rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_FEEDER_TO)** (master_data, parent_column): RelationshipRecord.Relationship.StartNode.NodeID has one RelationshipRecord.Relationship.EndNode.NodeID per role; holds 1.0, depth 3, ragged, orphans 0, cycles 7, invalid rows 7.
- **rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_FUND-MANAGED_BY)** (master_data, parent_column): RelationshipRecord.Relationship.StartNode.NodeID has one RelationshipRecord.Relationship.EndNode.NodeID per role; holds 1.0, depth 4, ragged, orphans 0, cycles 3194, invalid rows 3194.
- **rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_INTERNATIONAL_BRANCH_OF)** (master_data, parent_column): RelationshipRecord.Relationship.StartNode.NodeID has one RelationshipRecord.Relationship.EndNode.NodeID per role; holds 1.0, depth 3, ragged, orphans 0, cycles 5, invalid rows 5.
- **rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_SUBFUND_OF)** (master_data, parent_column): RelationshipRecord.Relationship.StartNode.NodeID has one RelationshipRecord.Relationship.EndNode.NodeID per role; holds 1.0, depth 4, ragged, orphans 0, cycles 15, invalid rows 15.
- **rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_ULTIMATELY_CONSOLIDATED_BY)** (master_data, parent_column): RelationshipRecord.Relationship.StartNode.NodeID has one RelationshipRecord.Relationship.EndNode.NodeID per role; holds 1.0, depth 4, ragged, orphans 0, cycles 3, invalid rows 3.

## Identifiers, sensitive columns and time

- **submissions.filings.recent**: identifiers: accessionNumber (record_key); event filingDate
- **submissions.filings.files**: identifiers: name (record_key); as of filingFrom–filingTo
- **submissions.formerNames**: as of from–to
- **submissions.tickers**: identifiers: value (record_key)
- **submissions**: identifiers: cik (record_key), ein (none), fiscalYearEnd (none); sensitive: phone (personal)
- **tickers**: identifiers: ticker (record_key)
- **lei2.Entity.LegalEntityEvents.LegalEntityEvent**: as at LegalEntityEventRecordedDate, event LegalEntityEventEffectiveDate
- **lei2.Registration.OtherValidationAuthorities.OtherValidationAuthority**: identifiers: ValidationAuthorityID (none)
- **lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress**: identifiers: @type (record_key)
- **lei2.Entity.OtherAddresses.OtherAddress**: identifiers: @type (record_key)
- **lei2.Extension.gleif:Geocoding**: identifiers: gleif:mapped_country (none); event gleif:geocoding_date
- **lei2.Entity.SuccessorEntity**: identifiers: SuccessorLEI (cross_reference, mod 97-10)
- **lei2**: identifiers: LEI (record_key, mod 97-10), Entity.RegistrationAuthority.RegistrationAuthorityID (none), Entity.LegalForm.EntityLegalFormCode (none), Registration.ManagingLOU (cross_reference, mod 97-10), Registration.ValidationAuthority.ValidationAuthorityID (none), Extension.leifr:FundNumber (cross_reference), Extension.leifr:FundManagerBusinessRegisterID (cross_reference, luhn), Extension.ext:CIF (cross_reference), Extension.leifr:SIREN (cross_reference, luhn), Extension.leifr:EconomicActivity.leifr:NACEClassCode (none), Extension.leifr:EconomicActivity.leifr:SousClasseNAF (none); as of Registration.InitialRegistrationDate–Registration.NextRenewalDate, as at Registration.LastUpdateDate
- **rr.RelationshipRecord.Relationship.RelationshipPeriods.RelationshipPeriod**: as of StartDate–EndDate
- **rr.RelationshipRecord.Relationship.RelationshipQuantifiers.RelationshipQuantifier**: identifiers: QuantifierAmount (record_key)
- **rr**: identifiers: RelationshipRecord.Relationship.StartNode.NodeID (record_key, mod 97-10), RelationshipRecord.Relationship.EndNode.NodeID (cross_reference, mod 97-10), RelationshipRecord.Relationship.RelationshipType (record_key), RelationshipRecord.Registration.ManagingLOU (cross_reference, mod 97-10); as at RelationshipRecord.Registration.LastUpdateDate
- **repex**: identifiers: LEI (record_key, mod 97-10), ExceptionCategory (record_key)

## Data quality to hand to data-quality

- submissions.formerNames: no_natural_key: no column or combination is unique
- submissions.tickers: link_not_found: values of value not found in tickers.ticker
- submissions.exchanges: no_natural_key: no column or combination is unique
- tickers: link_not_found: values of cik not found in submissions.cik
- lei2.Entity.LegalEntityEvents.LegalEntityEvent.AffectedFields.AffectedField: no_natural_key: no column or combination is unique
- lei2.Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress.AdditionalAddressLine: no_natural_key: no column or combination is unique
- lei2.Entity.OtherAddresses.OtherAddress.AdditionalAddressLine: no_natural_key: no column or combination is unique
- lei2.Entity.LegalAddress.AdditionalAddressLine: no_natural_key: no column or combination is unique
- lei2.Entity.HeadquartersAddress.AdditionalAddressLine: no_natural_key: no column or combination is unique
- lei2.Entity.OtherEntityNames.OtherEntityName: no_natural_key: no column or combination is unique
- lei2.Entity.LegalEntityEvents.LegalEntityEvent: no_natural_key: no column or combination is unique
- lei2.Registration.OtherValidationAuthorities.OtherValidationAuthority: no_natural_key: no column or combination is unique
- lei2.Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName: no_natural_key: no column or combination is unique
- lei2.Extension.gleif:Geocoding: no_natural_key: no column or combination is unique
- lei2.Entity.SuccessorEntity: no_natural_key: no column or combination is unique
- rr.RelationshipRecord.Relationship.RelationshipPeriods.RelationshipPeriod: no_natural_key: no column or combination is unique
- rr.RelationshipRecord.Relationship.RelationshipQualifiers.RelationshipQualifier: no_natural_key: no column or combination is unique
- rr: link_not_found: values of RelationshipRecord.Relationship.EndNode.NodeID not found in lei2.LEI
- repex.ExceptionReason: no_natural_key: no column or combination is unique
- repex.ExceptionReference: no_natural_key: no column or combination is unique

## Questions for the operator (one at a time)

1. Is submissions a new master kind named 'submissions'? Recommendation: yes: has a unique key (required); other parts point at it; points at few parts; has name-like text; has attributes besides codes and dates
2. Is tickers a new master kind named 'tickers'? Recommendation: yes: has a unique key (required); other parts point at it; points at few parts; has name-like text; has attributes besides codes and dates
3. Is lei2 a new master kind named 'lei2'? Recommendation: yes: has a unique key (required); other parts point at it; points at few parts; has name-like text; smaller than the parts pointing at it; has attributes besides codes and dates

Samples of personal columns are masked to their shape. Store suggestions are advice only.
