---
name: auto-ontology-product-query
description: Builds and qualifies business-question workflows in NVIDIA AutoOntology Chat/MCP from one or more Rules-derived data products. Use when creating a product-scoped query experience, question set, or business-answer workflow.
---

# AutoOntology product query interface

## Interface contract

Use AutoOntology's existing Chat UI and read-only MCP tools; this skill does not create a new web UI, CLI, or query service. The product list and table membership come from the side-effect-free `edgar-warehouse rules catalog plan`, not live OpenMetadata state or manually copied names. OpenMetadata remains the Rules-derived catalog. Read [AutoOntology setup](../auto-ontology/SKILL.md), [data catalog](../data-catalog/SKILL.md), and NVIDIA's [query skill](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-query/SKILL.md) first.

Each business fact has one authority: MDM owns mastered identities and relationships, RDM owns approved code sets, Silver owns transaction facts, and repository Rules/`CONTEXT.md` own definitions and processing policy. AutoOntology is a derived query layer. Do not write source data, rules, or OpenMetadata from this workflow.

## Assemble product scope

1. Ask which configured data product(s), user audience, and business questions are in scope. If the user said “all”, use all products in the Rules plan. Resolve names against the plan; never invent product IDs or table names.
2. For each selected `products[]` entry, treat `tables` as the product's asset list and `inputs` as its declared input ports. They are distinct associations. Preserve both roles in the scope record; deduplicate a physical table that belongs to multiple products, but keep every product membership.
3. Map each logical table to its configured MDM, RDM, or Silver database/schema/table. Do not infer a store by string splitting or connect raw source/capture tables merely because they appear as product inputs; include those only with separate authorization.
4. AutoOntology Chat/MCP has no documented `data_product_id` query filter. A product name in a prompt is context, not an access-control boundary. If product-level confidentiality is required, enforce it through database credentials and proven source-table allowlists (or a separately approved isolated deployment); if the selected release cannot prove the scope, use invented data and stop before connecting real stores.
5. For multiple products, qualify cross-product questions separately. Require an approved relationship or join path and matching grain; do not join on similar names or let an inferred relationship become business truth.

## Define and qualify questions

For every requested question, capture the product scope, business concept, measure, population, grain, time basis, filters, dimensions, allowed relationship path, and expected answer shape. Resolve definitions from Rules/`CONTEXT.md` and approved store contracts. Treat missing definitions, ambiguous measures, or unsupported joins as questions for the user, not guesses.

Use the selected release's setup and management skills for source connections and semantic edits. Require separate SELECT-only MDM/RDM/Silver credentials, inspect the release's sampling/embedding behavior, and obtain approval before external model inference. The local `auto-ontology` setup skill records the table-scope limitation; do not use production data until the exact release proves the required boundaries.

With invented or specifically approved test data, qualify each product and each cross-product path:

1. MCP `check_readiness` confirms a compiled layer and live source connection.
2. `search_terms` and `check_answerable` establish that the requested concepts are represented.
3. `ask_question` returns the answer, SQL, and rows. Inspect query intent, joins, filters, grain, `row_count`, and `truncated` before presenting the answer.
4. Include one unsupported question and require an explicit gap/refusal. A successful request is not proof that the result is correct.

## Publish the interface

Hand users the AutoOntology Chat/MCP entry point, supported product names, example business questions, and validated limitations. MCP signs in each caller and is read-only; use the current handshake/tool list. Keep connection management, semantic edits, model import, and compilation reset out of ordinary query access. Model import defaults to replacement and compilation reset is destructive; use neither as an automatic product sync.

Completion: every selected product resolves to Rules-defined assets and inputs; source scope is enforced or explicitly limited to test data; all supported questions pass SQL/row review; unsupported questions remain unanswerable; and no MDM, RDM, Silver, Rules, or OpenMetadata authority was changed.
