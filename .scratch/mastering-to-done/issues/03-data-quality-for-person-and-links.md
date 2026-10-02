# Data quality for Person and links

Type: grilling (HITL)
Status: resolved
Blocked by: 02

## Question

Data quality before the merge is built for Company (company mastering 22, #742).

Decide:
- which checks Person feed 1 and the relationship feeds need, such as name shape and the period checks;
- which of TestGen's checks to borrow (`data-quality/research/01-datakitchen-testgen-observability.md`);
- whether person names keep accents, apostrophes and degrees (person consumer contract 27).

## Answer

Operator, 2026-10-02 by 11:49 ET: "Proposed set (Recommended)".

**Critical checks.** A failure sets the record aside as an exception, and it never merges.

| On | Check |
|---|---|
| Person | CIK present and 10 digits |
| Person | The name has letters. It keeps accents, curly apostrophes and degree suffixes (Jr., PhD), and drops footnote marks. This closes person consumer contract 27. |
| Link | Both end identifiers present |
| Link | Capacity from the allowed set (director, officer, ten_percent_owner) |
| Link | Start no later than end |

**Run report checks** (TestGen style, from `data-quality/research/01-datakitchen-testgen-observability.md`). They are reported on every run and never block:
- row-count change from the last run;
- empty-value rate per field;
- age of the newest filing.

The build is ticket 18.
