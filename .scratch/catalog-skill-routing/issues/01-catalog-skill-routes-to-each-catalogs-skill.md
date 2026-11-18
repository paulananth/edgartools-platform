# The catalog skill is the top; each catalog's mechanics live in its own skill

Status: resolved
Type: task

Operator, 2026-11-18, asked which of two local OpenMetadata stacks should stay (they held about 2.5 GB together on an 8 GB
Mac): "edgartools-catalog is the top skill. Keep open metadata specific instructions in edgartools-openmetadata. We may support
more than one catalog".

## Findings

- The split already exists: `skills/data-catalog` holds the business meaning, the model and the publication outcomes through a
  "replaceable catalog or visualization destination" (it names OpenMetadata three times); `skills/openmetadata` holds the
  OpenMetadata mechanics and says business meaning stays in the catalog skill.
- What was missing for more than one catalog: nothing told an agent how to route by destination, or how another catalog is added.

## Parts

- [x] `data-catalog` gains "Choose the catalog's own skill": a table routing each destination to its skill, the rule that a
  catalog's mechanics stay out of this skill and its meaning out of the catalog's, and how another catalog is added (a sibling
  skill made as PORTABILITY.md says); its description no longer names OpenMetadata alone (2026-11-18 10:03 ET). Failing first:
  `test_the_catalog_skill_routes_each_destination_to_the_skill_that_owns_its_mechanics` (no such section, `AssertionError`) and
  `test_the_catalog_skills_description_names_no_single_catalog_as_its_scope` (the description began "Use for OpenMetadata catalog
  work"). Guarding the split, passing before and after: `test_the_catalog_skill_is_not_the_home_of_openmetadata_mechanics`,
  `test_the_openmetadata_skill_says_it_holds_only_that_catalogs_mechanics`
- [x] The local-server doc of the openmetadata skill says `edgartools-catalog` is the instance kept running and the isolated
  `edgartools-openmetadata` one is started for an isolated rebuild or test and stopped after (2026-11-18 10:02 ET; the skill lints pass)
- [x] The isolated `edgartools-openmetadata` stack (port 8587) is stopped, its volumes kept, so it can be started again; the
  `edgartools-catalog` stack (port 8585) runs (2026-11-18 10:02 ET; `docker ps`: three containers of `edgartools-catalog` remain)
- [x] Learning → skill: data-catalog "Choose the catalog's own skill"; openmetadata LOCAL-SERVER (2026-11-18 10:02 ET)
