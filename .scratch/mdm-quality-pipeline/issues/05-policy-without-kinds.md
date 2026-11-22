# Runtime gap: accepted policy without `kinds` fails in mastering

Type: task
Status: resolved
Priority: P0
Blocked by: none
Labels: wayfinder:task
Map: [MDM quality pipeline](../map.md)
Skill: [MDM Engineering](../../../skills/mdm-engineering/SKILL.md)

## Question

How should `mastering.merge` handle a policy accepted by validation when its optional `kinds` mapping is absent?

## Evidence

The approved D5 disposable PG16 scenario first failed in `mastering.merge.exact_namespaces` at line 60. After that reader was made safe locally, the same scenario failed in `_exact_rules` at line 529. Review also found `_waiting_sources` and `mastering.reads.carriers` directly indexing `kinds`. The fixture passes `check_policy` without `kinds`; no production store, provider data or feature switch was used.

The operator authorized a separate generic runtime fix and regression test in D7. Durable decision: `50f312f7-40c7-4c44-9add-d4e737191eb4`.

## Required behavior

- Every mastering rule and readback consumer uses the same optional-map semantics as `mdm.activation.check_policy`.
- Missing or null `kinds` means there are no per-kind rules; built-in `NAME_ID` remains available and no rule is invented.
- The fix is source-independent. No policy schema migration, source rule change or production quality-evidence switch is in scope.

## Approved regression scenario

- **Given** the existing synthetic policy fixture with no `kinds`, accepted by `check_policy`;
- **When** `mastering.merge` resolves exact-name namespaces, waiting sources and exact rules, and `mastering.reads.carriers` performs an empty-store lookup for a Company;
- **Then** the merge readers return the built-in namespace or empty rule sets, and carrier readback returns empty without `KeyError`.

The D5 disposable PG16 receipt-recovery test is a separate ticket-25 qualification gate. Its latest run stopped at `_exact_rules` before receipt generation; rerun it after this fix merges. No receipt-recovery PASS or production enablement is claimed here.

## Acceptance checklist

- [x] Run the focused accepted-policy regression covering exact namespaces, waiting sources, exact rules and carrier readback: `tests/mdm/test_policy_without_kinds.py` — 1 passed in 0.27s. (2026-11-22 11:26 ET)
- [x] Use one shared empty-map default for merge rules and the same validation default for carrier readback; no policy schema or production switch changed. (2026-11-22 11:26 ET)
- [x] Publish this ticket's change in PR #2025; all 12 CI jobs passed on code head `a59d5e5` (run #45046002178). The final ticket-closeout head remains draft until its current-head CI passes. (2026-11-22 12:12 ET)
- [x] Learning → MDM Engineering: the [Database-agnostic merge logic](../../../skills/mdm-engineering/SKILL.md#database-agnostic-merge-logic) now requires merge/readback readers to share validation's optional-map defaults. (2026-11-22 11:26 ET)

## Answer

`mastering.merge` centralizes per-kind rule lookup through `_kind_rules`, and `mastering.reads.carriers` uses the validator's empty-map default. The accepted-policy regression passed; CI passed all 12 jobs on code head `a59d5e5`. Ticket 25's receipt-recovery qualification remains separate and must be rerun after this fix merges. Production remains disabled.
