# Qualify the first SEC-to-GLEIF Company binding rule

Type: task
Status: open
Blocked by: 04

## Question

Operator, 2026-09-24: one real Company has **one** master record, holding the
CIK from SEC and the LEI from GLEIF; both source records stay in the Stage.
Two master records for one Company is the failure to prevent, not a state to
consolidate later.

Tickets 03 and 04 make a record recognisable again **by the identifier its own
source carries**: an SEC record by CIK, a GLEIF record by an LEI already on
the Company.
Neither joins the two sources. The SEC adapter declares `cik` as its only
identifier (`company_source.py:50`), GLEIF Level 1 carries no CIK, and Q14
forbids treating an LEI as a CIK crosswalk merely because both values exist.

SEC submissions **do** carry an `lei` key, but the adapter does not map it and
it was null for all four Companies checked on 2026-09-23 (Apple, Microsoft,
Shell, ASML; bronze `submissions/sec/cik=*/main/`). Where SEC populates it, the
record states its own LEI, which is not the crosswalk Q14 forbids and could be
an identifier path for part of the universe. **First step of this ticket:
measure how often it is populated across bronze**, which sets how much of the
join fuzzy matching must carry. For every Company without it, the first link
between its SEC and GLEIF records can only come from the qualified fuzzy
matching Company Q4 accepted: name, jurisdiction and address evidence,
corroborated where identifiers allow.

Without this ticket the Proving Run (05) reports every SEC Company as "no
GLEIF match", which Q2 counts as a *completed* outcome. The milestone would
look finished with zero SEC Companies linked to GLEIF, failing the completion
gate's order 4 ("Qualified automatic decisions tie SEC CIK and GLEIF LEI to one
immutable Company").

Build and qualify one fuzzy binding rule family for SEC → GLEIF Company:

- the candidate predicate and its named, versioned primitives, run inside the
  same Merge Stage transaction ticket 03 builds, never as a separate matcher;
- its statistical gate per the accepted policy — Company 99.9% precision at
  95% confidence, measured per rule family on a held-out set **independent** of
  the rule's authoring; the 308 adjudicated seed links are comparison only, not
  qualification truth;
- ambiguous candidates defer and contribute no GLEIF fields (Q2, Q6);
  a verified no-match is a completed outcome only after the rule has actually
  run;
- a wrong link is reversible through evidence-bound reversal, and a Match
  Exclusion stops it recurring.

Out of this ticket: consolidating two already-published Company IDs (Q10, Q11
keep their own gate) and GLEIF-only parent creation (Q7).

## Why it sits after 04

The fuzzy rule proposes a link to a Company that already exists by CIK. The
identifier path must be in place first, so the rule's candidates are the
established masters and not per-record fresh mints.

## What 05 and 06 inherit

The Proving Run reports this family's verdicts beside the identifier rules',
and the activation approval names its digest separately: approving the
identifier rules does not approve this one.
