# Decide which evidence may bind a source record to a Person Identity

Type: grilling
Status: open
Blocked by: none (15 resolved; Q2 re-posed on its facts)

## Question

Per source, what is sufficient to bind a record to an existing Person
Identity or create one, given the repo rule that name similarity alone
never binds and Clean MDM's Q11/Q16 disabling unqualified automatic rules:

- `owner_cik` (Form 3/4/5): deterministic — one CIK, one Person?
- CRD number (Form ADV individual registrant): deterministic?
- Proxy and 8-K names: bind only through a deterministic **context key**
  (same issuer CIK + normalized name + consistent role/flag from a
  reporting-owner row), never name alone? Or Steward review only until a
  calibrated matcher exists?

Also: uniqueness (one active CIK per Person, one active CRD per Person) and
the veto when a CIK and a CRD claim the same person but names disagree.

## Comments

- 2026-09-20, Q1 (`owner_cik`): operator chose **(a)** — `owner_cik` binds
  a Person deterministically, one CIK ↔ one Person enforced in both
  directions, second claimant vetoed to Steward review, and only after
  ticket 03 classifies the row as a natural person.
- 2026-09-20, Q2 (CRD): posed as "CRD never binds a Person; ADV attaches as
  a profile on a CIK-bound Person." Operator: "research differences between
  CRD and owner_cik and if needed they need to be merged to form a unique
  identifier; need full understanding before deciding." Opened
  [ticket 15](15-research-crd-vs-cik-identifier-semantics.md); Q2 waits.
