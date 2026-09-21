# Write the Source Contract spec and the Codex handover

Type: task
Status: resolved (2026-09-21)
Blocked by: 07

## Question

Nothing to decide. Write the spec from the resolved tickets and the
prototype, including the Mapping Language reference (ticket 01) and a worked
example per proof source. Write the Codex handover for Clean MDM gaps (new
identifier formats, deferring a record whose relationship target is missing,
anything else ticket 01 or 07 found).

## Handover items collected so far

Send together in one note (operator, 2026-09-21), not piecemeal:

1. **Test mode for automatic rules** (research 03): the local runner may
   evaluate a candidate rule that is not active, and never publishes the
   result, so a mastering case can assert "the rule bound this record to X"
   before the rule has its proof. The Q16 amendment itself is already with
   Codex (`.scratch/handover/2026-09-20-claude-to-codex-mastering-policy-language.md:21`).
2. **A readiness wait of at least 30 s** in the shared Postgres fixture
   (`tests/integration/test_clean_mdm_postgres.py:65-73`, ~8 s today; 4 of 7
   runs failed on Colima).
3. **A named offline registry authority** for local tests
   (`docs/specs/clean-mdm/local-operations.md:46-47` forbids manufacturing
   activation authority).
4. Contract validation, `lei` format, formatted relationship targets,
   deferral instead of silent relationship drops, and a versioning path for
   an immutable dataset body (research 01).
5. **Author the Mastering Policy in the Source Contract's convention**
   (ticket 04 Q2a): strict YAML 1.2 → canonical JSON, same paths, same
   `primitive: {arguments}` calls, a JSON Schema; plus a kind-level
   `default_sources` list with per-field exceptions.
6. **Kind at mapping time vs classification in the policy** (prototype
   finding 2): let a Dataset Contract defer the identity kind to the
   Mastering Policy's classification rules (e.g. rule C-J), or carry a
   provisional kind the policy may override.

## Answer

Written:
- **Spec:** [`docs/specs/source-contract/spec.md`](../../../docs/specs/source-contract/spec.md).
  It is self-contained for a contract author: the file format, the path
  grammar, all 23 primitives, lookups, the three Custom Step shapes and their
  six rules, `silver`, `dataset` (the adapter reference, condensed), checks,
  Named Cases, the Batch Gate, output and exit codes, `source run`, no-network,
  the Mapping Document, the lifecycle and activation, and the complete GLEIF
  contract as its worked example. It carries the prototype's limits verbatim.
  Two dependencies block go-live and have their own sections: the immutable
  Dataset Contract (§23) and the identity kind at mapping time (§13.4).
- **Handover:** [`.scratch/handover/2026-09-21-claude-to-codex-source-contract.md`](../../handover/2026-09-21-claude-to-codex-source-contract.md).
  It leads with GLEIF, because Codex is building that loader now (this
  replaces the separate heads-up note), then lists the 5 blocking requests
  apart from the rest.
- **Check 7:** six contract terms were missing from `CONTEXT.md` and are
  now defined: Artifact Family, Primitive, Named Convention, Custom Step,
  Named Case, Batch Gate.
- **New finding while writing (15):** YAML 1.2 alone still types `010`,
  dates and `1e3`. The real loader must read plain scalars as text (spec §6).
