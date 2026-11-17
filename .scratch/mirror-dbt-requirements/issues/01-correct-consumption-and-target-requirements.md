# Correct mirror consumption and dbt destination requirements

Status: claimed
Type: task

## Operator ruling

Direct consumption of approved mirror tables does not need dbt. Gold remains
the intended downstream transformation layer, but its database and schema names
are not approved. The previously written Gold destination is not naming authority.
This change does not rename or drop existing objects or activate consumers.

## Checklist

- [x] Correct skills and dbt requirements: direct read-only consumption first;
  use dbt for required Gold transformations with an explicitly approved target.
  Verified by Spec review; 2026-11-17 06:40 ET.
- [x] Decouple Postgres ingress provisioning from creation of a Gold schema;
  two rendered-SQL cases failed before the fix because gold_schema was still
  required, then both passed with only control-location parameters; 2026-11-17 06:40 ET.
- [x] Verify affected tests, genericity, guide paths and Standards/Spec/GoF review:
  2 SQL cases and 127 documentation checks passed; all three reviews found no
  blockers or worthwhile pattern refactor; 2026-11-17 06:40 ET.
- [ ] Publish the checked change for review and retain CI status in the handoff.
- [x] Learning → skill: GOLD.md dbt implementation requirements and the operations
  skill now separate naming approval from existing operational objects, and
  decouple connectivity from Gold creation; 2026-11-17 06:40 ET.
