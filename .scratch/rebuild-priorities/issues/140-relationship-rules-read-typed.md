# 140: The relationship engine reads each type's rules as typed fields

Priority: 140. Map: [Rebuild priorities](../map.md). Opened 2026-10-27 18:53 ET.

Type: task. Status: resolved.
Blocked by: [132](132-relationship-types-in-one-place.md) merging. Raised by 132's
three-axis review (GoF and Spec).

## Why

Ticket 132 made one Rust module, `relationship_types.rs`, read and check the
relationship types from their RDM code set as a typed rule set (`TypeRules`).
The calculation in `relationships.rs` still reads each rule by name from an
untyped object (13 read sites: `values::has_value(spec, "keeps_start")` and so
on), so a misspelt key there reads as absent and passes the check. New type
rules have landed five times (#836, #850, #851, #1107, 132), each editing the
check and the string reads by hand.

## Parts

- [x] ( ET) `prepare_relationships` takes the types as `TypeRules` (parse once); the calculation reads typed fields; the string reads and `spec: &Object` parameters go
- [x] ( ET) The agent context reads each relationship type's definition from the code set the active policy pins, not the repo's pin (`context.relationship_definitions`)
- [x] ( ET) The ultimate-parent algorithms are named once (the check's list and the calculation's `match`)
- [x] Tests ( ET): cargo test (all pass, plus the typed-rules test and one that refuses a rule's name in `relationships.rs`); tests/mdm, tests/unit, tests/architecture (2469); the relationship walk on PostgreSQL (`tests/storage_adapters/test_normal_master_reads.py`, 8)
- [x] Learning → skill ( ET): `skills/data-onboarding/REFERENCE.md` says a new type rule is one typed field and its check, read through an accessor
