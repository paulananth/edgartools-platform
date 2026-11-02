# 167: Tables carry their processing layer

Priority: 167. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 07:00 ET (operator, 2026-11-02: "classification is missing", then "mdm, rdm, silver").

Type: task. Status: resolved. Blocked by: none.

## Question

The skill names a `processing_layer` classification, but the publisher never wrote it (the skill said "not written yet"). Which tags, and on which tables?

Answer: three tags, `mdm`, `rdm`, `silver`, on every table of those stores (45 tables). A source dataset carries none.

## Parts

- [x] GoF consult: leave `_data_classes`; one small function beside it, marks published by the existing loop (2026-11-02 07:00 ET)
- [x] The plan carries the classification and one mark per table (`test_master_reference_and_silver_tables_carry_their_processing_layer`, 2026-11-02 07:00 ET)
- [x] `check` reports a missing class or layer tag (`test_publish_tags_each_table_with_its_layer_and_check_says_when_a_tag_is_missing`, 38 pass, 2026-11-02 07:00 ET)
- [x] Live: published, `check` matched, tags read back: mdm 20, rdm 13, silver 12, sources 0 (2026-11-02 07:00 ET)
- [x] Learning → skill: `skills/openmetadata/SKILL.md` says the layer tag is written and `check` sees it
