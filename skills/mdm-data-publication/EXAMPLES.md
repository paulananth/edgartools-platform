# MDM Data Publication Examples

## Examples

An assignment can be represented in configuration as:

```yaml
exposures:
  - source:
      database: <source_database>
      schema: <source_schema>
      table: <final_table>
    output:
      layer: mirror
      database: <consumer_database>
      schema: <consumer_schema>
      object: <published_object>
    purpose: <business_purpose>
    consumer: <consumer_role_or_product>
    grain: <one_row_per_business_identity_or_fact>
    time_scope: <current_state_or_declared_history>
    evidence:
      requirements: <approved_requirement>
      profiling: <profile_result>
      modeling: <model_contract>
      approval: <approval_record>
    status: approved
```

A published reference-value table can be consumable while its restricted
editing table stays internal. An approved parent-child relationship view can
be exposed while match candidates and steward decisions remain hidden.
