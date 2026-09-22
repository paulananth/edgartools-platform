# Prove identifier-only Company binding through a verified Identifier Contract

Type: task
Status: open
Blocked by: 03

## Question

Company Q14. An exact, compatible identifier resolving to **one** Company
reuses that immutable Company ID, with no separate precision study. Implement
and prove it for the SEC CIK and the GLEIF LEI:

- declare the namespace, issuing authority, normalization and primitive
  versions, scope and cardinality, and the compatibility checks, in the pinned
  policy;
- verify the contract to activate the rule (verification, not a statistical
  gate);
- an identifier that is missing, ambiguous, conflicting, suspended or of an
  unsupported namespace **defers**; it never binds;
- an LEI never establishes a CIK crosswalk merely because both values exist;
- a name change or a lapsed registration alone never revokes a binding (Q9).

Fuzzy binding and published-ID consolidation stay refused here: they keep
their own statistical gates.
