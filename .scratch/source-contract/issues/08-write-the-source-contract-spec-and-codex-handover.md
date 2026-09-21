# Write the Source Contract spec and the Codex handover

Type: task
Status: open
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
