# The Person link engine

Type: task (code)
Status: in progress (Claude, branch `claude/mastering-14-person-link-engine`)
Blocked by: 02

## Question

The engine catches up to the Person spec for the Forms 3/4/5 family (ticket 02 answer; `docs/specs/person/consumer.md`, "Relationship types" and "Temporal behavior"):
- the `CONTROLS` type, next to `EMPLOYED_BY`, with the capacity set by the rules; `INSIDER_OF` gives way to an `IS_INSIDER` view;
- a link keyed by Person, Company and capacity, with the title as a dated detail;
- a date basis (stated or observed) on each date, and a link with only an observed start allowed;
- the omission closer (a later same-issuer filing that drops the capacity);
- a stated end contradicted by a later filing goes to a steward.

Build it on synthetic records first; the Forms 3/4/5 reader is ticket 10. GoF consult first, then PostgreSQL 16 tests.

## Checklist

- [x] GoF consult: leave the structure; write the sighting fold as its own pure function, and keep capacities in their own table. 2026-10-02 12:25 ET
- [x] `CONTROLS` next to `EMPLOYED_BY`, each with its capacities; a link with any other capacity goes to review: `test_a_capacity_the_type_does_not_have_goes_to_review`. 2026-10-02 12:47 ET
- [x] `INSIDER_OF` removed; an `mdm.is_insider` view over the two types, Section 16 capacities only (migration `004_is_insider.sql`, tested on a populated store). 2026-10-02 12:47 ET
- [x] A link keyed by Person, Company and capacity; the officer title a dated detail of the period: `test_one_link_per_person_company_and_capacity`, `test_the_title_is_a_dated_detail_of_the_period`. 2026-10-02 12:47 ET
- [x] Dated sightings (observed or stated, held or dropped) folded into periods, each date with its basis; an observed start is enough: `fold_sightings`, 8 unit tests. 2026-10-02 12:47 ET
- [x] The omission closer: a later filing that drops the capacity ends the period at its event date; a later sighting opens a new period: unit and PostgreSQL 16 tests. 2026-10-02 12:47 ET
- [x] A sighting after a stated end does not reopen the link; it goes to a steward (an open, blocking `contradicts_stated_end` review): unit and PostgreSQL 16 tests. 2026-10-02 12:47 ET
- [x] Unit tests of the fold (`tests/mdm`), PostgreSQL 16 tests through the Merge Stage (`tests/integration`): 13 + 3 new pass; 412 MDM/unit tests naming the engine pass; 28 relationship, schema, index, run and fresh-mastering integration tests pass. 2026-10-02 12:47 ET
- [ ] Three-axis `/code-review` (Standards, Spec, GoF), findings fixed
- [ ] PR, CI green, merge on the operator's word
