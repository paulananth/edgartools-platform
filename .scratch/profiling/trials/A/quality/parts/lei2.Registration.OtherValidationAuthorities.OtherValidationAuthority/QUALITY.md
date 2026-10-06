# Data quality plan: lei2.Registration.OtherValidationAuthorities.OtherValidationAuthority

Version **Trial A-lei2.Registration.OtherValidationAuthorities.OtherValidationAuthority-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| code_list_other_validation_authority_id | in_set@1 | fields.other_validation_authority_id | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.

## New code (log a ticket; not written)

| Check | Column | Rows | Notes |
|---|---|---|---|
| no_natural_key | None | 0 | the designed record key is filled and unique |
