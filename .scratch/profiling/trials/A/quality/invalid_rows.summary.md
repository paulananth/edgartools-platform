# Invalid hierarchy rows, Trial A

7170 rows marked (the full file stays out of the repository: 3.8 MB; `invalid_rows.sample.jsonl` holds the first 200).

| Rows | Hierarchy | Reason | Outcome |
|---|---|---|---|
| 3192 | rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_FUND-MANAGED_BY) | names itself as its parent | needs steward |
| 986 | submissions.filings.recent: isXBRLNumeric > form | isXBRLNumeric differs | fix with evidence |
| 440 | lei2: Entity.RegistrationAuthority.RegistrationAuthorityID > Registration.ValidationAuthority.ValidationAuthorityID | Entity.RegistrationAuthority.RegistrationAuthorityID differs | fix with evidence |
| 405 | rr: RelationshipRecord.Relationship.RelationshipStatus > RelationshipRecord.Registration.ManagingLOU | RelationshipRecord.Relationship.RelationshipStatus differs | fix with evidence |
| 405 | rr: RelationshipRecord.Relationship.RelationshipStatus > RelationshipRecord.Registration.ValidationDocuments | RelationshipRecord.Relationship.RelationshipStatus differs | fix with evidence |
| 405 | rr: RelationshipRecord.Relationship.RelationshipStatus > RelationshipRecord.Registration.RegistrationStatus | RelationshipRecord.Relationship.RelationshipStatus differs | fix with evidence |
| 353 | lei2: Entity.LegalAddress.@xml:lang > Entity.HeadquartersAddress.@xml:lang | Entity.LegalAddress.@xml:lang differs | fix with evidence |
| 298 | lei2.Extension.gleif:Geocoding: gleif:match_level > gleif:geocoding_failed > gleif:mapped_country > gleif:mapped_state | gleif:mapped_country differs | fix with evidence |
| 297 | submissions: flags > ownerOrg > sicDescription > sic | ownerOrg differs | fix with evidence |
| 204 | lei2: Entity.LegalAddress.Country > Entity.LegalJurisdiction | Entity.LegalAddress.Country differs | fix with evidence |
| 24 | lei2: Entity.RegistrationAuthority.RegistrationAuthorityID > Registration.ValidationAuthority.ValidationAuthorityID | Entity.RegistrationAuthority.RegistrationAuthorityID differs | needs steward |
| 22 | lei2: Entity.EntityStatus > Registration.RegistrationStatus | Entity.EntityStatus differs | fix with evidence |
| 13 | submissions: flags > ownerOrg > sicDescription > sic | flags differs | fix with evidence |
| 13 | submissions: flags > fiscalYearEnd | flags differs | fix with evidence |
| 13 | submissions: flags > addresses.business.stateOrCountry | flags differs | fix with evidence |
| 13 | submissions: flags > category | flags differs | fix with evidence |
| 13 | submissions: flags > entityType | flags differs | fix with evidence |
| 12 | submissions: flags > stateOfIncorporation | flags differs | fix with evidence |
| 10 | rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_SUBFUND_OF) | on a cycle of parents | needs steward |
| 6 | lei2: Entity.LegalAddress.@xml:lang > Entity.HeadquartersAddress.@xml:lang | Entity.LegalAddress.@xml:lang differs | needs steward |
| 6 | rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_FEEDER_TO) | on a cycle of parents | needs steward |
| 5 | submissions: addresses.mailing.isForeignLocation > addresses.mailing.stateOrCountry | addresses.mailing.isForeignLocation differs | fix with evidence |
| 5 | rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_INTERNATIONAL_BRANCH_OF) | names itself as its parent | needs steward |
| 5 | rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_SUBFUND_OF) | names itself as its parent | needs steward |
| 4 | rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_DIRECTLY_CONSOLIDATED_BY) | names itself as its parent | needs steward |
| 4 | rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_DIRECTLY_CONSOLIDATED_BY) | on a cycle of parents | needs steward |
| 3 | lei2.Extension.gleif:Geocoding: gleif:match_level > gleif:geocoding_failed > gleif:mapped_country > gleif:mapped_state | gleif:mapped_country differs | needs steward |
| 3 | rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_ULTIMATELY_CONSOLIDATED_BY) | names itself as its parent | needs steward |
| 2 | lei2: Entity.HeadquartersAddress.Country > Entity.HeadquartersAddress.Region | Entity.HeadquartersAddress.Country differs | fix with evidence |
| 2 | lei2: Entity.EntityCategory > Extension.leifr:LegalFormCodification > Entity.LegalForm.EntityLegalFormCode | Entity.EntityCategory differs | fix with evidence |
| 2 | rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_FUND-MANAGED_BY) | on a cycle of parents | needs steward |
| 1 | submissions.filings.recent: isXBRLNumeric > form | isXBRLNumeric differs | needs steward |
| 1 | lei2: Entity.LegalAddress.Country > Entity.LegalAddress.Region | Entity.LegalAddress.Country differs | fix with evidence |
| 1 | lei2: Entity.LegalAddress.Country > Entity.LegalJurisdiction | Entity.LegalAddress.Country differs | needs steward |
| 1 | lei2: Entity.EntityStatus > Entity.EntitySubCategory | Entity.EntityStatus differs | fix with evidence |
| 1 | rr: RelationshipRecord.Relationship.StartNode.NodeID → RelationshipRecord.Relationship.EndNode.NodeID (IS_FEEDER_TO) | names itself as its parent | needs steward |
