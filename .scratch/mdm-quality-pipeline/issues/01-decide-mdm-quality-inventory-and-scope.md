Type: grilling
Status: resolved
Blocked by: none
Labels: `wayfinder:grilling`

## Checklist

- [x] Record the approved evidence threshold, evaluation grains, source inventory, and failure-action policy. 2026-11-13 19:02 ET
- [x] Add the linked decision summary to the map. 2026-11-13 19:02 ET
- [x] Validate the ticket and map update with `git diff --check` and the overlap guard. 2026-11-13 19:02 ET
- [x] Learning → skill: none; no reusable skill change was identified. 2026-11-13 19:02 ET

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

## Answer

Approved by the operator on 2026-11-13:

- Inventory both configured source checks and proposed checks grounded in an
  explicit master-contract requirement or an observed defect. Do not invent
  checks for uniform coverage.
- Allow source-record, complete-delivery/publication, and persisted-master-state
  evaluation grains. Assign each check the narrowest grain that fits its
  requirement.
- Preserve configured failure actions. For a proposed check whose failure
  action is not specified by its contract, leave that action unresolved; do
  not default to `flag`, `withhold`, or `exception`.

The current Company, Person, and Security inventory has 20 source-specific,
record-grain check declarations:

| Domain | Source | Configured checks and failure actions |
|---|---|---|
| Company | SEC company | `name_present` (`exception`); `address_not_registered_agent` and `street_not_placeholder` (`withhold`); `state_code_known` (`flag`) |
| Company | GLEIF | `name_present` (`exception`); legal-address `address_not_registered_agent` and `street_not_placeholder`, plus `headquarters_not_registered_agent` and `headquarters_street_not_placeholder` (`withhold`) |
| Person | SEC submissions; SEC ownership | Each declares `legal_name_present` and `legal_name_has_letter` (`exception`) |
| Person | IAPD ADV | `filing_name_present` and `custodian_name_present` (`exception`) |
| Security | N-PORT | `placeholder_name_of_issuer` (`withhold`); `cusip_check_digit` and `share_class_one_letter` (`flag`) |
| Security | 13F | `cusip_check_digit` and `share_class_one_letter` (`flag`) |

All current check kinds used here are implemented by the shared MDM quality
engine in `edgar_warehouse/mdm/quality.py`. The inventory review found no
additional check supported by an explicit master-contract requirement or an
observed defect beyond these configured checks. Identifier-format validation
and identifier claim uniqueness/capacity remain separately listed mastering
invariants, not counted as quality checks. No delivery-wide or persisted-master
check is currently configured. The Company Financials silver suggestions and
DataKitchen TestGen test types are not added as MDM rules.

No new check kind or evaluation scope needs implementation based on this
inventory; later tickets decide the execution and evidence contract for the
existing record-grain checks.
