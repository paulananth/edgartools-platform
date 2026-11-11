# OpenMetadata resync scope (2026-11-11)

## Decision

The operator asked to "resync openmetadata reinit and resync from source". Read as
three steps: reinitialize the server through the repository entrypoint, reset the
owned catalog objects, and publish the current rules plan from source.

## Owned scope

Established by comparing every live object with the current plan
(`edgar-warehouse rules catalog plan --root rules`, built from `origin/main` at
`3884e81b`).

| Object | Live | Plan | Owned |
|---|---|---|---|
| DatabaseService | 1 (`edgartools-rules`) | 1 | yes |
| PipelineService | 15 | 14 | yes, all 15 (the plan's 14 plus the retired shared service) |
| Pipeline | 22 | 85 | yes |
| Table | 69 | 72 | yes |
| Database | 4 | 5 | yes |
| Schema | 24 | 25 | yes |
| Domain | 8 | 8 | yes |
| Glossary | 8 | 8 | yes |
| GlossaryTerm | 23 | 23 | yes |
| DataProduct | 3 | 3 | yes |
| TestCase | 57 | 61 | yes |
| TestDefinition | 27 | 2 owned | only the two configured ones |
| Classification | 6 | 1 owned | only `data_class` |
| Tag | 20 | 4 owned | only `master_data`, `reference_data`, `relationship`, `transaction_data` |

Not owned, and preserved: the built-in classifications (`Certification`,
`KnowledgeCenter`, `PersonalData`, `PII`, `Tier`), the built-in tags (`Article`,
`Bronze`, `Gold`, `HowToGuide`, `NonSensitive`, `None`, `Personal`, `QuickLink`,
`Sensitive`, `Silver`, `SpecialCategory`, `Tier1`..`Tier5`), the workflows, the
roles, the users and the instance settings.

The live catalog predates the per-step Pipeline design: it holds 22 target-level
Pipelines, where the current plan holds 85 (the targets plus each visible step).
That is the main thing a resync brings.

## The server recreate

`bash infra/openmetadata/init.sh` recreated the server container. Docker could not
stop the running container (`cannot stop container: ... tried to kill container,
but did not receive an exit event`), leaving a `Created` replacement beside the
running original. The original then exited 137 (SIGKILL) and left port 8585
unbound. Both containers were removed and compose brought the stack up again.

The `edgartools-catalog_db-data` and `edgartools-catalog_es-data` volumes were
preserved and the PostgreSQL data directory was intact. No `down -v`, no database
drop, no search-storage clear.

## Order of work

1. Reinit: `bash infra/openmetadata/init.sh` for the idempotent demo exclusion
   and readback.
2. Reset: delete in dependency order — owned products, owned quality cases, owned
   custom quality definitions, every owned PipelineService, the database
   service, owned glossary terms, owned glossaries, owned domains, then owned
   custom tags.
3. Resync: `rules catalog publish` from the current plan.
4. Verify: `rules catalog check` independently, plus the domain and glossary
   inventories and the absence of any forbidden shared object.

## Outcome (2026-11-11)

All four steps completed. `rules catalog check` returns `confirmed`, readback
`matched`, no differences, 5 of 5 quality results confirmed.

### What the reset had to work around

- **Test case deletion needs `recursive=true`.** Without it the server refuses
  with `testCase is not empty`; the case carries a resolution-status child row.
  With it the cascade succeeds.
- **Quality case ownership is by entity link, not by name.** The plan renames
  cases as a source's version moves (v1 to v2), so an exact-name match leaves
  stale cases behind. Every live case whose `entityLink` names the
  `edgartools-rules` service is owned.
- **`Certification.Gold` and `Certification.Silver` are built-in system
  entities.** The server refuses to delete them
  (`System entity [Gold] of type tag can not be deleted`). They stay and the
  publisher reuses them; only the four `data_class.*` tags are ours and go.
- **The token expires within the hour.** A publish that answers 401 needs a
  fresh login token, refreshed through `POST /api/v1/users/login` per the
  skill's private-shell procedure.

### The quality evidence

Five per-load results were held by three cases. They were captured before the
reset (`.scratch/openmetadata-resync-20261111/live-quality-results.json`),
converted to the publisher's `--results` format, and republished. The
`sec.nport.registrant` case moved from v1 to v2 with the same check id, so its
result was remapped to the v2 case. All five are back with their original
timestamps and load references.

### Two mistakes made during verification

- A probe that PUT `{}` to the 52 domain-lineage edges blanked their
  descriptions. A second `rules catalog publish` restored them; all 52 now
  match the plan. The description lives in `lineageDetails.description`, not
  the edge's top-level `description`.
- The domain lineage probe was a write, not a read. Read the lineage, never
  write to it, when checking.

### Final state, independently read through the API

| Object | Count | Matches the plan |
|---|---|---|
| database services | 1 | yes |
| pipeline services | 14 | yes, exact set |
| pipelines | 85 | yes, exact set |
| tables | 72 | yes, exact set |
| databases | 5 | yes, exact set |
| schemas | 25 | yes, exact set |
| domains | 8 | yes |
| glossaries | 8 | yes |
| glossary terms | 23 | yes |
| glossary relations | 23 | yes (46 stored; the server materializes both directions) |
| data products | 3 | yes, every planned asset present |
| quality cases | 61 | yes, exact set |
| quality results | 5 | yes |
| data class marks | 45 | yes, exact set |
| certifications | 51 | yes, exact set |
| table profiles | 6 | yes |
| table-to-domain memberships | 18 | yes, exact set |
| table lineage edges | 32 | yes, descriptions match |
| pipeline-to-table edges | 88 | yes, descriptions match |
| pipeline-to-pipeline edges | 31 | yes, descriptions match |
| inbound table-to-pipeline edges | 28 | yes, descriptions match |
| domain lineage edges | 52 | yes, descriptions match |

Built-ins preserved: the 5 other classifications, 16 built-in tags, 25 test
definitions, the workflows, roles, users and instance settings.

The catalog survives a server restart with every count unchanged.
