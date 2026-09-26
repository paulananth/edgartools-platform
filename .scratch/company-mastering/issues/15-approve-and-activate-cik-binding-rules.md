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
  publish time, and a real concurrent-run test. Built (Claude, 2026-09-26):
  ticket 04, "Closing the five open safety items".
- [ ] The operator answers two questions (ticket 04, "Suspended identifier"):
  1. When a Company is in review because its own records disagree on an
     identifier (for example two SEC records naming two CIKs), should the
     matching rules stop adding any record to it until the conflict is
     resolved? Built that way; the record waits in the Stage with a review.
  2. Should an identifier stated by a source that does not issue it (a
     GLEIF record carrying a CIK) be able to put a Company in review at
     all? Today it can; it does not arise under today's adapters.
- [ ] Verify CIK uniqueness, conflicting or stale identifiers, duplicate and
  reordered delivery, idempotent retry, and no unapproved consolidation on
  PostgreSQL 16.
- [ ] Record the operator-approved fingerprint, activation time, full proof, and
  resulting active fingerprint before shared registration.
