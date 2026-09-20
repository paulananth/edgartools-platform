# Decide how Form 3/4/5 reporting owners are classified as Person vs entity

Type: grilling
Status: open
Blocked by: none

## Question

`sec_ownership_reporting_owner` mixes natural persons (directors, officers)
with entities (10% owners that are funds, holding companies, trusts). A
reporting-owner row with `is_ten_percent_owner` and no officer/director
flag is usually not a person. What rule classifies each row's kind —
`person`, `company`, `fund_structure`, or deferred — before any binding is
attempted, and what happens to a row whose kind cannot be decided from
flags and name (deferred with a blocking review, per Clean MDM's
`deferred_record`, never coerced)?
