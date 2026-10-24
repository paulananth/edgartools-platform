# Is a named attestation enough to approve a rule

Type: grilling
Status: open
Blocked by:

## Question

Rules approval records the approver's name and the database login that wrote the row. It does not require a second login. An earlier migration checked membership in `rules_approver` and was replaced on purpose. Is the named attestation the rule we want to keep, or must a different database login approve?

Do not treat the removed membership check as a defect until this decision says so.

## Checklist

- [ ] Grilling with the operator. Do not answer for them.
- [ ] Learning → skill: record the decision in the rules skill only if the operator changes the rule.
