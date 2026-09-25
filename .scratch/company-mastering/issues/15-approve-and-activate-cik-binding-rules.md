# Approve and activate the CIK binding rules

Type: task
Status: open
Blocked by: 04, 05, 06
Blocks: automatic SEC Company creation and SEC-to-GLEIF name-rule activation

## Outcome

Present the exact policy fingerprint and verified Identifier Contract for the
CIK binding rules already implemented by ticket 04. Obtain separate operator
approval, then activate only the approved rules and register that exact policy.
The approval of ticket 08's declared name rules does not activate these.

## Checklist

- [ ] Close the ticket 04 safety items: suspended identifiers, recheck of an
  existing Company before saving, crash recovery of assessments, caller as-of
  publish time, and a real concurrent-run test.
- [ ] Verify CIK uniqueness, conflicting or stale identifiers, duplicate and
  reordered delivery, idempotent retry, and no unapproved consolidation on
  PostgreSQL 16.
- [ ] Record the operator-approved fingerprint, activation time, full proof, and
  resulting active fingerprint before shared registration.
