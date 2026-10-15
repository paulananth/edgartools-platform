# README: architecture, skills, mastering and Data Catalog

Owner: Codex. Branch: `codex/readme-architecture-20261015`.

## Scope

Rewrite the project README for executives and architects. Recreate the
architecture diagrams, explain the repository's skills and mastering, and
show how approved profiling and Rules publish metadata to the Data Catalog.
Describe current implementation separately from activation and deployment.
Only README, diagram artifacts and this workstream's records are owned here.

## Checklist

- [x] Inspect current main, code, domain vocabulary, skills, catalog and source status. — inspected origin/main 3eee39f2, CONTEXT, catalog/profile generators, MergeStage and current source contracts; 2026-10-15 07:24 ET.
- [x] Review the relevant design and history with the GoF method; record the verdict. — reviewed MergeStage/identity/catalog code and history: retain existing facade, scope and plain-function design; documentation only; 2026-10-15 07:24 ET.
- [x] Rewrite the README with executive context and an architectural explanation. — README draft covers business outcomes, nine operational skills, mastering and catalog lineage; source and integration boundaries explicit; 2026-10-15 07:24 ET.
- [x] Recreate and render the architecture and mastering diagrams, including editable sources. — platform, mastering and catalog rendered as SVG/PNG/native Excalidraw; all visually inspected; 2026-10-15 07:26 ET.
- [x] Validate links, command examples, diagram rendering and factual claims; review Standards, Spec and GoF. — 57 links/anchors; five command forms and three live worker descriptions; 8 catalog tests passed; three-axis review in VERIFICATION.md; 2026-10-15 07:26 ET.
- [x] Run the overlap guard and preserve the reviewed documentation on the dedicated branch. — guard passed for 15 files; documentation committed locally on the dedicated Codex branch; 2026-10-15 07:26 ET.
- [x] Revalidate the branch against current main and complete the ship audits. — main already current; fresh 57-link/diagram/CLI checks and 8 catalog tests (6.96 s); independent coverage, plan and Standards/Spec/GoF audits pass; 2026-10-15 07:39 ET.
- [ ] Push the documentation branch and create the pull request.
- [ ] Verify the PR base/head and report CI status.
- [x] Learning → skill: assess whether this documentation task uncovered a reusable skill correction. — none; existing skill contracts explained, no behavior changes; 2026-10-15 07:26 ET.
