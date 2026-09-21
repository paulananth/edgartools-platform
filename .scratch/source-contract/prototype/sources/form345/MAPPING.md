# Mapping Document — `sec.ownership` vprototype-1

Generated from `contract.yaml` (digest `cc7ecf5f3390`). Do not edit by hand.

## `sec_ownership_reporting_owner`  (one row per `reportingOwner`)

| Silver column | Type | From the Bronze Artifact | Into MDM |
|---|---|---|---|
| `accession_number` | string | `header` `ACCESSION NUMBER` | record key |
| `owner_index` | bigint | `ordinal` | record key |
| `owner_cik` | bigint? | `int` `reportingOwnerId.rptOwnerCik.$` | identifier `cik` |
| `owner_name_raw` | string | `text` `reportingOwnerId.rptOwnerName.$` | field `name` |
| `owner_name` | string | **custom** `owner_display_name@1` | evidence only |
| `owner_kind` | string | **custom** `owner_kind@1` | identity kind |
| `is_director` | boolean | `flag` `reportingOwnerRelationship.isDirector.$` | evidence only |
| `is_officer` | boolean | `flag` `reportingOwnerRelationship.isOfficer.$` | evidence only |
| `is_ten_percent_owner` | boolean | `flag` `reportingOwnerRelationship.isTenPercentOwner.$` | evidence only |
| `is_other` | boolean | `flag` `reportingOwnerRelationship.isOther.$` | evidence only |
| `officer_title` | string? | `text` `reportingOwnerRelationship.officerTitle.$` → `when` → `empty_to_null` | evidence only |
| `issuer_cik` | bigint? | `int` `issuer.issuerCik.$` | evidence only |
| `other_text` | string | `text` `reportingOwnerRelationship.otherText.$` | evidence only |
| `filing_footnote_text` | string | `join` `footnotes.footnote` | evidence only |
| `filing_remarks` | string | `text` `remarks.$` | evidence only |
| `address_is_care_of` | boolean | `text` `reportingOwnerAddress.rptOwnerStreet1.$` → `upper` → `strip_spaces` → `starts_with` `'C/O'` | evidence only |
| `address_non_us` | boolean | `flag` `reportingOwnerAddress.rptOwnerNonUSAddressFlag.$` | evidence only |
| `owner_submissions_present` | boolean | `ref` `owner_submissions` → `get` `found` | evidence only |
| `owner_submissions_sha256` | string | `ref` `owner_submissions` → `get` `artifact_sha256` | evidence only |
| `owner_entity_type` | string | `ref` `owner_submissions` → `get` `payload.entityType` → `to_text` | evidence only |
| `owner_sic` | string | `ref` `owner_submissions` → `get` `payload.sic` → `to_text` | evidence only |
| `owner_state_of_incorporation` | string | `ref` `owner_submissions` → `get` `payload.stateOfIncorporation` → `to_text` | evidence only |
| `owner_ein` | string | `ref` `owner_submissions` → `get` `payload.ein` → `to_text` | evidence only |
| `owner_ticker_count` | bigint | `ref` `owner_submissions` → `len` `payload.tickers` | evidence only |
| `owner_org` | string | `ref` `owner_submissions` → `get` `payload.ownerOrg` → `to_text` | evidence only |
| `owner_fiscal_year_end` | string | `ref` `owner_submissions` → `get` `payload.fiscalYearEnd` → `to_text` | evidence only |
| `parser_version` | string | `const` `'source-contract:prototype-1'` | evidence only |

## `sec_ownership_non_derivative_txn`  (one row per `nonDerivativeTable.nonDerivativeTransaction`)

| Silver column | Type | From the Bronze Artifact | Into MDM |
|---|---|---|---|
| `accession_number` | string | `header` `ACCESSION NUMBER` | — |
| `owner_index` | bigint | `const` `1` | — |
| `txn_index` | bigint | `ordinal` | — |
| `security_title` | string | `value_with_footnotes` `securityTitle` | — |
| `transaction_date` | date? | `date_prefix` `transactionDate.value.$` | — |
| `transaction_code` | string | `text` `transactionCoding.transactionCode.$` | — |
| `transaction_shares` | double? | `number` `transactionAmounts.transactionShares.value.$` | — |
| `transaction_price` | double? | `number` `transactionAmounts.transactionPricePerShare.value.$` | — |
| `acquired_disposed_code` | string | `text` `transactionAmounts.transactionAcquiredDisposedCode.value.$` | — |
| `shares_owned_after` | double? | `number` `postTransactionAmounts.sharesOwnedFollowingTransaction.value.$` | — |
| `ownership_direct_indirect` | string | `text` `ownershipNature.directOrIndirectOwnership.value.$` | — |
| `ownership_nature` | string | `text` `ownershipNature.natureOfOwnership.value.$` | — |
| `reporting_owner_count` | bigint | `count` `reportingOwner` | — |
| `parser_version` | string | `const` `'source-contract:prototype-1'` | — |

## `sec_ownership_derivative_txn`  (one row per `derivativeTable.derivativeTransaction`)

| Silver column | Type | From the Bronze Artifact | Into MDM |
|---|---|---|---|
| `conversion_or_exercise_price` | double? | `number` `conversionOrExercisePrice.value.$` | — |
| `exercise_date` | date? | `date_prefix` `exerciseDate.value.$` | — |
| `expiration_date` | date? | `date_prefix` `expirationDate.value.$` | — |
| `underlying_security_title` | string | `value_with_footnotes` `underlyingSecurity.underlyingSecurityTitle` | — |
| `underlying_security_shares` | double? | `number` `underlyingSecurity.underlyingSecurityShares.value.$` | — |
| `accession_number` | string | `header` `ACCESSION NUMBER` | — |
| `owner_index` | bigint | `const` `1` | — |
| `txn_index` | bigint | `ordinal` | — |
| `security_title` | string | `value_with_footnotes` `securityTitle` | — |
| `transaction_date` | date? | `date_prefix` `transactionDate.value.$` | — |
| `transaction_code` | string | `text` `transactionCoding.transactionCode.$` | — |
| `transaction_shares` | double? | `number` `transactionAmounts.transactionShares.value.$` | — |
| `transaction_price` | double? | `number` `transactionAmounts.transactionPricePerShare.value.$` | — |
| `acquired_disposed_code` | string | `text` `transactionAmounts.transactionAcquiredDisposedCode.value.$` | — |
| `shares_owned_after` | double? | `number` `postTransactionAmounts.sharesOwnedFollowingTransaction.value.$` | — |
| `ownership_direct_indirect` | string | `text` `ownershipNature.directOrIndirectOwnership.value.$` | — |
| `ownership_nature` | string | `text` `ownershipNature.natureOfOwnership.value.$` | — |
| `reporting_owner_count` | bigint | `count` `reportingOwner` | — |
| `parser_version` | string | `const` `'source-contract:prototype-1'` | — |

**MDM kind:** from `owner_kind`.  **Custom:** 2 of 60 columns (3.3%).
