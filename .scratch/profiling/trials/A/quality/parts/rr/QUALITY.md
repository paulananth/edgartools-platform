# Data quality plan: rr

Version **Trial A-rr-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| placeholder_relationship_record_relationship_relationship_status | placeholder@1 | fields.relationship_record_relationship_relationship_status | withhold | 345 |
| placeholder_relationship_record_registration_validation_reference | placeholder@1 | fields.relationship_record_registration_validation_reference | withhold | 3 |
| code_list_relationship_record_relationship_relationship_status | in_set@1 | fields.relationship_record_relationship_relationship_status | flag | 0 |
| code_list_relationship_record_registration_registration_status | in_set@1 | fields.relationship_record_registration_registration_status | flag | 0 |
| code_list_relationship_record_registration_managing_lou | in_set@1 | fields.relationship_record_registration_managing_lou | flag | 0 |
| code_list_relationship_record_registration_validation_sources | in_set@1 | fields.relationship_record_registration_validation_sources | flag | 0 |
| code_list_relationship_record_registration_validation_documents | in_set@1 | fields.relationship_record_registration_validation_documents | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.

## New code (log a ticket; not written)

| Check | Column | Rows | Notes |
|---|---|---|---|
| link_not_found | RelationshipRecord.Relationship.EndNode.NodeID | 469556 | the value is a key of the part it points at (args.to) |
| hierarchy_invalid | RelationshipRecord.Relationship.RelationshipStatus | 405 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | RelationshipRecord.Relationship.RelationshipStatus | 405 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | RelationshipRecord.Relationship.RelationshipStatus | 405 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | None | 8 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | None | 7 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | None | 3194 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | None | 5 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | None | 15 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
| hierarchy_invalid | None | 3 | the row's parent exists, is not the row itself, is not on a cycle, and is the parent its code has; each invalid row is in invalid_rows.jsonl |
