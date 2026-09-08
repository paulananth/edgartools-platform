Type: task
Status: open

Blocked by: 01

## Question

Design and implement the equivalent closing/deactivation mechanism for
`EMPLOYED_BY` (`_derive_employed_by`, `edgar_warehouse/mdm/pipeline.py:3400`)
that Ticket 02 designs for `IS_INSIDER` -- same root cause, different
source shape (`sec_executive_record`/DEF 14A compensation table +
`sec_employment_event`/8-K Item 5.02, two independently-watermarked source
tables per this method's own docstring, vs. `IS_INSIDER`'s single source).

Live evidence: `EMPLOYED_BY` shows 51.7% overall quarantine, and 97.8%
(6,767 of 6,919) for rows created since PR #568 landed -- the highest
post-fix rate of any type, since (like `IS_INSIDER`) it has zero existing
deactivation logic and every genuine year-over-year compensation or title
update for an already-known (person, company) pair is a same-source
conflict by construction.

## Answer

(not yet resolved)
