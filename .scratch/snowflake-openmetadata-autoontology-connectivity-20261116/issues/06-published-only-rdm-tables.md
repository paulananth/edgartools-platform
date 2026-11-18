# RDM tables that hold published versions only

Status: open
Type: task
Owner: Claude

## Question

RDM's tables hold draft code-set versions beside published ones (8 of its 9 tables; only `rdm.code_path` is written
at publish alone), so no whole RDM table is a final output (data-platform FINAL-TABLES.md). The published-only form
exists as the view `rdm.code_context`, which the managed mirror cannot carry. Operator, 2026-11-17: "Published-only
RDM tables (Recommended)".

## Checklist

- [ ] Design the published-only tables (written once when a version is published, as `rdm.code_path` is), with the data-modeling skill
- [ ] Build and prove them on a disposable store: a draft never appears, a published version appears once, a retired one keeps its rows
- [ ] Add them to `rules/exposure.yaml`
- [ ] Learning → skill

Blocked by: 01
