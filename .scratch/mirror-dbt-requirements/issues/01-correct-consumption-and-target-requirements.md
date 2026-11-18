# Correct mirror consumption and dbt destination requirements

Status: resolved
Type: task

## Operator ruling

Direct consumption of approved mirror tables does not need dbt. Gold remains
the intended downstream transformation layer, but its database and schema names
are not approved. The previously written Gold destination is not naming authority.
This change does not rename or drop existing objects or activate consumers.
The operator clarified that Gold consists of dimensions and facts, with
separate entity dimension views for Person, Company and Security. Physical
view names remain undecided.
The operator then required the skill to be generic for any domain. Approved
configuration defines the entity/fact list; a shared modeling path handles it,
with no fixed entity list or domain-specific copy. No generator is claimed live.

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
- [x] Publish the locally checked change for review: PR #1860 is draft while
  final-head CI is pending; 2026-11-17 06:41 ET.
- [x] Complete final-head CI and merge; retain the draft on failure or pending
  validation. No live rollout is part of this change. PR #1860 merged with
  12 of 12 checks green on its final head 91bfc1eb; 2026-11-17 20:38 ET.
- [x] Record separate Gold entity dimension views, shared master keys and
  independent fact grains in GOLD.md and modeling requirements; verified by
  focused documentation checks; 2026-11-17 06:45 ET.
- [x] Generalize the modeling/dbt requirements to any configured domain and
  entity/fact list, using shared templates with explicit capability checks;
  verified by genericity and guide-path checks; 2026-11-17 06:45 ET.
- [x] Compare against the recent Gold method in PR #1850, the semantic-view
  skill and data-engineering fundamentals: retain one fact per grain, shared
  conformed dimensions, code-set versions, separate time roles and conditional
  history. Clarify cross-domain reuse and ordinary SQL views versus certified
  Semantic Views; verified by document comparison and guide checks; 2026-11-17 06:45 ET.
- [x] Learning → skill: GOLD.md dbt implementation requirements and the operations
  skill now separate naming approval from existing operational objects, and
  decouple connectivity from Gold creation; 2026-11-17 06:40 ET.
