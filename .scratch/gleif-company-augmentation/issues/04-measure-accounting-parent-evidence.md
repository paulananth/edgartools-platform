# Measure accounting-parent and exception evidence

Type: research
Status: resolved
Blocked by: 02

## Question

For adjudicated company-to-LEI links, how often does GLEIF add direct or
ultimate accounting-consolidation parents, and how often does it instead report
a typed exception or no usable relationship record?

## Required evidence

- Join only through accepted LEIs to the fixed Level 2 relationship and
  reporting-exception publications.
- Report direct-parent, ultimate-parent, both-parent, exception, inactive or
  retired relationship, and missing-evidence counts separately.
- Preserve relationship type, validity periods, registration evidence,
  corroboration, and exception category.
- Compare with existing MDM parent and subsidiary evidence without collapsing
  accounting consolidation into generic parenthood.
- Identify parent LEIs that are outside the 1,000-company cohort without
  forcing them into MDM.

## Done when

Relationship lift and absence semantics are quantified on accepted links and no
missing record is presented as an affirmative no-parent assertion.

## Answer

Resolved by [`../research/04-parent-exception-results.md`](../research/04-parent-exception-results.md).

Among 308 accepted Company-to-LEI links, 23 have both direct and ultimate
accounting-consolidation records, seven have an ultimate record plus a direct
reporting exception, 255 have both exception categories, and 23 have neither.
Only three relationship records have both endpoints accepted within the cohort;
all other parent endpoints remain unresolved source evidence. No same child/type
has both a current relationship and exception, and no missing record is treated
as a no-parent assertion.
