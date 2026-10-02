# The Person link engine

Type: task (code)
Status: open
Blocked by: 02

## Question

The engine catches up to the Person spec for the Forms 3/4/5 family (ticket 02 answer; `docs/specs/person/consumer.md`, "Relationship types" and "Temporal behavior"):
- the `CONTROLS` type, next to `EMPLOYED_BY`, with the capacity set by the rules; `INSIDER_OF` gives way to an `IS_INSIDER` view;
- a link keyed by Person, Company and capacity, with the title as a dated detail;
- a date basis (stated or observed) on each date, and a link with only an observed start allowed;
- the omission closer (a later same-issuer filing that drops the capacity);
- a stated end contradicted by a later filing goes to a steward.

Build it on synthetic records first; the Forms 3/4/5 reader is ticket 10. GoF consult first, then PostgreSQL 16 tests.
