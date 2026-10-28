# 140: The relationship engine reads each type's rules as typed fields

Priority: 140. Map: [Rebuild priorities](../map.md). Opened 2026-10-27 18:53 ET.

Type: task. Status: open, not started.
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

- [ ] `prepare_relationships` takes the types as `TypeRules` (parse once); the calculation reads typed fields; the string reads and `spec: &Object` parameters go
- [ ] The agent context reads each relationship type's definition from the code set the active policy pins, not the repo's pin (`context.relationship_definitions`)
- [ ] The ultimate-parent algorithms are named once (the check's list and the calculation's `match`)
- [ ] Tests, three-axis review, PR, CI green, merge
- [ ] Learning → skill
