# The catalog skill is the top; each catalog's mechanics live in its own skill

Status: open
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
- [x] I stopped the isolated `edgartools-openmetadata` stack (port 8587) to save memory, reading the operator's answer as a
  choice of stack; the repository's tooling targets that stack (`init.sh` refuses any other URL; credentials and publish default
  to it), so it broke the catalog init and publish path. Restarted, both stacks run (2026-11-18 10:06 ET; `docker ps`). The decision stays
  open: see part 5
- [x] Spec review, three findings fixed (2026-11-18 10:06 ET): the generic skill named the OpenMetadata publisher's commands
  (`rules catalog plan|publish|check`; the test caught only `publish`: `AssertionError: ['rules catalog plan', 'rules catalog plan']`
  once it covered all three), the sibling-skill pointer went to a file that does not describe a skill's layout (it now points
  to the openmetadata skill's layout and PORTABILITY for qualification), and the duplicated processing-layer rule in the
  openmetadata skill is a link
- [ ] The operator decides which stack to retire, for memory: the prior `edgartools-catalog` (8585, whose compose file is not in the
  repository) or `edgartools-openmetadata` (8587, which every script targets). Recommendation: retire the prior one; the tooling
  needs 8587
- [ ] ~~Business-meaning passages in the openmetadata skill move to data-catalog~~ deferred to
  .scratch/catalog-skill-routing/issues/02-move-business-meaning-out-of-the-openmetadata-skill.md: glossary scope rules (lines
  233-250) and the domain-membership rule (182-183) are generic, and moving them touches the skill's references
- [x] Learning → skill: data-catalog "Choose the catalog's own skill"; openmetadata LOCAL-SERVER (2026-11-18 10:02 ET)
