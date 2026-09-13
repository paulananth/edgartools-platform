# Decide accepted-link publication policy

Type: grilling
Status: resolved
Blocked by: 02, 11

## Question

Which GLEIF identity evidence may create or retain an active MDM source link
without manual stewardship, and what happens to every lower-confidence
candidate?

## Recommendation

Auto-link only from a previously approved active LEI link or a verified
authoritative/certified identifier crosswalk whose domain semantics and
uniqueness checks pass. Route heuristic Tier B and C candidates to review and
reject Tier D. The 308 manually adjudicated cohort links may seed a tracer
bullet only with their complete retained evidence; they do not establish a
general auto-link rule.

## Done when

The allowed evidence classes, confidence/review states, uniqueness invariant,
revalidation trigger, unlink behavior, and audit fields are explicit.

## Answer

An active link may publish only when it is a previously approved link that
revalidates against the current source, or when a verified authoritative or
certified identifier crosswalk passes domain semantics and one-active-binding
uniqueness checks. Tier B and C heuristic candidates require stewardship; Tier
D is rejected. The 308 adjudicated links are seed evidence, not a general rule.

Revalidate on a changed LEI record, changed mapping, conflicting candidate,
successor/duplicate/retired status, monthly reconciliation, or rule-version
change. Business-close rather than delete a failed link, preserve the prior
decision, and require a new decision before successor rebinding. Retain source,
publication, record hash, run, rule version, evidence class, reviewer/reason,
observed/effective validity, status, and supersession lineage.

Accepted by the user during the 2026-09-12 `/grill-with-docs` session.
