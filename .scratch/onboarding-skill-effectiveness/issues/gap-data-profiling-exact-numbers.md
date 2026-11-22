# Capability gap: the profiler reads some numbers through floating point

Type: task
Status: open
Priority: P0
Blocked by: none
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-profiling](../../../skills/data-profiling/SKILL.md)

## Question

How does `profile_data.py run` keep every decimal and every all-digit identifier exact, for every tabular and record format, with no source-specific code?

## Evidence

Ticket 11's approved scenario requires exact identifiers and decimals. Prior exploratory probes used invented inputs and the real `profile_data.py run`; these were not committed tests.

- A zipped CSV decimal with at most two decimal places and one 17-digit integer part was profiled and specified as `DOUBLE`. Its `decimal_places` was 20 rather than 2 because the scientific-notation form of the float was counted.
- A JSON array of 60 records with distinct 22-digit integer identifiers was profiled as `DOUBLE`, with `distinct: 5` instead of 60.
- A CSV all-digit identifier with leading zeroes remained `VARCHAR`, and a 22-digit CSV identifier was read as `HUGEINT`.

The approved scenario's exact-number outcome is therefore not expressible by the current generic reader for the demonstrated CSV decimal and JSON integer cases. This ticket records the gap; it does not change profiler runtime code.

## Required behavior

- One generic reading path across supported formats; no value passes through `DOUBLE` before profiling, key selection, distinct counts or silver typing.
- Decimal text remains exact, with measured digits and decimal places.
- Integers wider than `BIGINT` retain every digit or the run refuses and names the column.
- Tests on invented input assert exact stored type, `decimal_places` or `distinct`, and silver type. The two demonstrated cases must fail on current code; only add other formats after a probe demonstrates a failure.

## Ticket 11 linkage

[Ticket 11](./11-data-profiling-generic-verification.md) remains incomplete until this capability is fixed and verified.
