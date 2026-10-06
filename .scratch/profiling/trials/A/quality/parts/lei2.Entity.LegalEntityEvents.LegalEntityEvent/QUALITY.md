# Data quality plan: lei2.Entity.LegalEntityEvents.LegalEntityEvent

Version **Trial A-lei2.Entity.LegalEntityEvents.LegalEntityEvent-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| code_list_group_type | in_set@1 | fields.group_type | flag | 0 |
| code_list_event_status | in_set@1 | fields.event_status | flag | 0 |
| code_list_legal_entity_event_type | in_set@1 | fields.legal_entity_event_type | flag | 0 |
| code_list_validation_documents | in_set@1 | fields.validation_documents | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.

## New code (log a ticket; not written)

| Check | Column | Rows | Notes |
|---|---|---|---|
| no_natural_key | None | 0 | the designed record key is filled and unique |
