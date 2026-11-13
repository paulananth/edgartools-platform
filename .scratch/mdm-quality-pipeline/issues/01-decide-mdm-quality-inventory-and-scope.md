Type: grilling
Status: open
Blocked by: none
Labels: `wayfinder:grilling`

# Decide the MDM Quality Inventory and Scope

## Question

Which checks belong in the Company, Person, and Security MDM pipelines, and at
what grain should each check evaluate?

Distinguish current source-record checks in `quality.yaml`, MDM identifier
claim constraints, and DataKitchen TestGen test types. For each proposed check,
settle whether it evaluates one mapped record, a complete delivery/publication,
or persisted master state; identify whether the current shared engine can run
it; and preserve its intended failure action. Keep the nine Company Financials
silver recommendations separate unless evidence shows a specific rule belongs
to an MDM entity contract.

The answer should leave an approved per-domain inventory and identify only the
generic check kinds or evaluation scopes that need implementation. Do not
invent checks to make asset coverage counts look uniform.
