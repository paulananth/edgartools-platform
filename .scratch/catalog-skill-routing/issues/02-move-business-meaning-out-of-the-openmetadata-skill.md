# Move the business-meaning passages out of the openmetadata skill

Status: open
Type: task

Split from `01-catalog-skill-routes-to-each-catalogs-skill.md` (Spec review). The openmetadata skill (499 lines, at its limit)
says business meaning stays in the data-catalog skill, yet holds some:

## Parts

- [ ] Glossary scope rules (a platform word's home is `CONTEXT.md`; silver field definitions go on the column, not in the
  glossary): move to data-catalog, leave the OpenMetadata mapping
- [ ] The domain-membership rule (a dataset is a member of the kind it becomes; a relationship type is not a member of its endpoint
  domains): move the rule, keep "the server draws edges" here
- [ ] The operator's approval of `Source-aligned` for master-data domains: the approval is business meaning, the type name is
  OpenMetadata's; split them
- [ ] Learning → skill: data-catalog and openmetadata, each holding its own
