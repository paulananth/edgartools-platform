# Decide which evidence may bind a source record to a Person Identity

Type: grilling
Status: open
Blocked by: none (11–14 resolved)

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
