# The company rule, phase 2

Status: open
Type: task
Owner: claude (map decisions 1 to 6, 8)
Blocked by: 01

A new version of `sec-company-candidate`: no ticker filter; `investment` is a company before the fund-word test; an `other`
filer with a legal-form word is a company unless fund-named, Form-D-only or person-suffixed; commodity pools, asset-backed
issuers and governments stay Set Aside.

## Checklist

- [ ] The rule version, with a descriptive name, and the contract naming it
- [ ] Tests per step (one per kind of filer), failing on today's rule
- [ ] Proved on the captured 76,230 submissions: counts by verdict and step, against the simulation (18,645 new companies)
- [ ] The operator's approval of the version, in their words, against that evidence (data-onboarding APPROVE)
- [ ] `/code-review`
- [ ] Learning → skill
