# Custom parsing outside configuration

Status: in progress — testing configuration replacement candidates; production unchanged
Branch: `codex/custom-parsing-research-20261002`
Base: `542a9fa04f4359bed7e097b4cb1d5fa4b89ede15` (origin/main, fetched 2026-10-02 09:31 ET)

## Request

Create a brand new branch and research whether custom parsing code exists
outside configuration-driven parsing. Inspect current source and executable
callers; keep acquisition decoding, configurable field mappings, and control
validation distinct so the findings identify actual source-specific logic.

## Checklist

- [x] Create a dedicated Codex worktree and branch from fetched current main — git fetch and git worktree add; shared dirty files preserved; 2026-10-02 09:31 ET.
- [x] Inventory custom parsing in runtime packages and runnable scripts, with primary-source file and caller evidence — background research inspected Python, Rust, scripts and infrastructure; caller chains recorded in docs/research/custom-parsing-inventory-2026-10-02.md; 2026-10-02 09:39 ET.
- [x] Trace the configuration-driven path and verify which behaviors are configured versus fixed in Python — canonical rules loader and CLI probe confirmed three source documents/five Dataset Contracts, no read block, fixed Company operation names and config-selected adapter formats; source_input, adapters, quality and primitives inspected; 2026-10-02 09:36 ET.
- [x] Record active, uncalled and historical parsing findings in a research report, with limits of the evidence — separates reachable Python source readers, config-selected primitives, retained helpers, external-library smoke tools, generic validation and configured Rust prototype; source baseline and absence of deployment proof explicit; 2026-10-02 09:39 ET.
- [x] Verify report references and branch diff — 68 source links and line anchors resolve; staged git diff --check passes; only the research report and this ticket changed; 2026-10-02 09:41 ET.
- [x] Commit and publish the research documents on the owned branch, then verify the remote head — 84a3cb6b pushed; git ls-remote confirms matching remote SHA; 2026-10-02 09:42 ET.
- [x] Review candidate code and history using GoF guidance; select bounded experiments without adding new production parsing features — adapters/GLEIF/Company history includes #742, #754, #759, #771 and #773; existing function registries provide the test seam, no new GoF class hierarchy justified; 2026-10-02 10:01 ET.
- [x] Test existing Python configuration against custom projections, classification and rejection behavior using pinned cases — 41 passed, zero failures/skips, JUnit counts verified; includes shared XML golden projection and independent rejection counterexamples; 2026-10-02 10:12 ET.
- [x] Test the Rust configuration prototype against native XML projection and rejection cases; record which runtime integration is missing — background researcher verified 13 passed, unchanged engine; README records standalone prototype and observed CDATA/header/namespace gaps; 2026-10-02 10:12 ET.
- [x] Write recommendations based on measured equivalence and counterexamples, with runnable evidence and explicit limits — configuration-replacement-results-2026-10-02.md distinguishes partial projection, missing wiring and retained gates; 2026-10-02 10:14 ET.
- [ ] Verify and publish the experiment results and updated research report.

## Scope

Research, reproducible experiments and documentation only. Existing Grok parsing worktrees and Claude's
mastering continuation are separate workstreams. Production code, approved
rules and existing tests remain unchanged. Experimental configurations are
not registered or approved runtime rules. Root Codex owns Python experiments,
this ticket and the result report. The background researcher owns only its
Rust experimental artifacts, with file ownership assigned in its task.

## Verification evidence

The read-only local probe used `uv run --no-project` with the existing primary
Python environment and this worktree on PYTHONPATH. It asserted that the loaded
rules module belongs to this worktree, built the executable CLI parser, and
loaded every source through `edgar_warehouse.rules.files.load_source`.

- CLI routes: resolve-snowflake-env, mdm, bookkeeping, rules, change-journal.
- Three source folders: gleif, sec.submissions.company, sec.submissions.person.
- Five Dataset Contracts: GLEIF Level 1, relationships and reporting exceptions;
  SEC Company; SEC Person. No source, contract or adapter declares `read`.
- Company configuration selects company.expand, company.silver and company.prepare;
  their implementations are registered Python capabilities.
- Adapter identifier formats `lei` and `sec_cik` resolve to fixed Python handlers.

This is source/CLI/configuration verification, not a database integration test
or evidence that a source runs in a hosted deployment.

Research and document verification took approximately 11 minutes (09:31–09:42
ET), including background source/caller inventory and the configuration probe.

Follow-up experiment implementation and documentation took over ten minutes
(10:01–10:14 ET for implementation and documentation), including the 41 Python comparisons and 13 Rust probes.
These research tests characterize matches and incompatibilities; they are not
full pipeline qualification or a CI speed benchmark. The result report records
commands and dependency reuse. Production behavior and registered rules are
unchanged.
