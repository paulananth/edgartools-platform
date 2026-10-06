# Data quality plan: rr.RelationshipRecord.Relationship.RelationshipPeriods.RelationshipPeriod

Version **Trial A-rr.RelationshipRecord.Relationship.RelationshipPeriods.RelationshipPeriod-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| code_list_period_type | in_set@1 | fields.period_type | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.

## New code (log a ticket; not written)

| Check | Column | Rows | Notes |
|---|---|---|---|
| no_natural_key | None | 0 | the designed record key is filled and unique |
