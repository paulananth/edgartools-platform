# Rust engine core behind Python

Type: task (code)
Status: in progress (Claude, branch `claude/mastering-15-rust-engine`)
Blocked by: 08

## Question

Build the configured source engine in Rust (`crates/source-contract`), called only from Python (ticket 08).

- **Python binding:** a PyO3 module built with maturin, plus a thin Python facade in `edgar_warehouse/rules/`. The warehouse and MDM Docker images build and install the binding.
- **Readers:** json, jsonl, xml, csv and zip, with bounded memory. XML must keep CDATA and reject malformed input, a wrong root, namespace, header or count, and a DTD.
- **Primitives** for paths, formats and checks, declared in the rules files.
- **Custom steps:** named Python callbacks the rules file declares, used only as the last resort.
- **Acceptance:** Codex's research suites (`docs/research/experiments/custom-parsing/`, and the Rust probes, now `crates/source-contract/tests/acceptance.rs`). Each counterexample that blocks a replacement there must now pass.

**Open design points**, settled at the start of the ticket:
- the facade's API;
- how a custom step is registered;
- how the engine reports a deferred record versus a failed one.

GoF consult first, then the three-axis review.

## Decisions (Claude, 2026-10-02 13:27 ET; the operator may overrule)

The operator asked for fewer questions, so I settled the three open points myself:

1. **The facade's API.** `edgar_warehouse/rules/source_engine.py`: `SourceEngine(contract)` takes a rules-file contract (a dict). Its `.read(data, lookups=None)` returns `Reading(tables, deferred)`. Nothing else in Python imports the Rust module.
2. **How a custom step is registered.** A rules file names a step with its version (`custom: {step: blank_missing_token@1, ...}`). The step is a Python function in one registry, `edgar_warehouse/rules/steps.py`. A step the contract names that has no function fails when the contract loads, never partway through a read.
3. **A deferred record versus a failed one.**
   - **Deferred:** a record check written `on_fail: defer` sets that record aside, with the `reason` the rules file gives. Rules files reuse the reasons the readers already emit, such as `gleif_deletion_flag` and `ambiguous_relationship_period`. A deferred record carries its raw record, shaped as the Python readers shape it (`$` for text, `@x` for attributes).
   - **Failed:** a document check, or a record check written `on_fail: reject`, fails the whole artifact. It raises `SourceRejected(code, detail)`. A reader that moves onto the engine (tickets 16 and 17) turns that into its own `Conflict`.

**Packaging.**
- The binding is its own package in `crates/source-contract`, built by maturin. It uses `abi3-py312`, and PyO3 sits behind the cargo feature `python`.
- The main project reaches it through an `engine` extra, so the other CI jobs and worktrees don't compile Rust.
- A new CI job runs `cargo test` and the engine tests in `tests/engine`.
- The two dependency images build the wheel in a Rust stage and install it.

**Memory.** Every read is bounded by declared limits: artifact bytes, ZIP member bytes and records. A read over a limit fails closed. Records are not streamed: each artifact is read into memory, up to its limits.

**13F.** The prototype returned an empty success for a wrong root or bad XML. Now both fail closed. 13F is not on the engine yet, so nothing in production changes.

## Checklist

- [x] Baseline: `cargo test --locked`, 16 passed (13 research, 3 13F). 2026-10-02 13:27 ET
- [x] GoF consult: leave it. The crate has 2 commits and no repeated change. Each format is one reader function into the shared tree; the primitives stay one `match`; steps keep the name registry. 2026-10-02 13:27 ET
- [x] Acceptance first: the research counterexamples, turned around, in `crates/source-contract/tests/acceptance.rs`; they did not compile against the prototype's API before the change. 2026-10-02 15:32 ET
- [x] XML: keep CDATA; reject malformed input, a wrong root or namespace, a DTD (with or without entities), a missing or repeated required path, and a record count that disagrees: `cdata_is_kept`, `a_bad_document_fails_closed`. 2026-10-02 15:32 ET
- [x] Readers for json, jsonl, csv and zip (exactly one unencrypted member), with declared limits on bytes, member bytes and records. 2026-10-02 15:32 ET
- [x] Primitives: `date` (to UTC), `const`; record checks `required`, `in_set`, `in_lookup`, `absent`, `count`, `before`, `lei`, each deferring or rejecting, with an optional `when`; a path can select from a list (`Name[sub.path=VALUE]`). Checks run in the rules file's order, so the first reason wins, as in the Python readers. 2026-10-02 15:32 ET
- [x] Custom steps: a Python callback by name, checked when the contract loads; a step that raises fails the artifact (`step_failed`). 2026-10-02 15:32 ET
- [x] PyO3 binding (`--features python`, abi3), `edgar_warehouse/rules/source_engine.py` facade and `steps.py` registry; 7 tests in `tests/engine`, plus `tests/architecture/test_engine_boundary.py` (only the facade imports the engine). 2026-10-02 15:32 ET
- [x] Packaging: the `engine` extra, the CI job (`cargo test`, then `tests/engine`) and a Rust stage in both deps Dockerfiles. `Dockerfile.mdm-deps` was built locally in 567 s (1.15 GB), and the binding read a record inside it. The deps image tag now hashes the crate, so a crate-only change rebuilds it; CLAUDE.md's rebuild table says so. The warehouse deps Dockerfile has the same stage, unbuilt locally. 2026-10-02 15:43 ET
- [x] Map Codex's 41 Python and 13 Rust research tests to 15, 16, 17 or "stays code". 2026-10-02 15:32 ET

  | Research tests | Count | Where |
  |---|---|---|
  | Rust probes (all 13) | 13 | 15: turned around in `acceptance.rs` |
  | Python: Rust fixture projection, CDATA, the seven XML mutations | 9 | 15: `acceptance.rs` (`projects_both…`, `cdata_is_kept`, `a_bad_document_fails_closed`) |
  | Python: Level 1 mapping, scope and deletion gates, invalid category, shared LEI check | 6 | 16: the engine has the checks (`in_lookup`, `absent`, `in_set`, `lei`), and 16 writes them into the GLEIF rules file |
  | Python: relationship projection, its six gates, the singleton list and the offset date | 10 | 16: list selection (`[PeriodType.$=…]`), `count`, `before`, `required` with `when`, and `date` to UTC cover them |
  | Python: SEC Company scalar lookups, `mapped_field` versus a Silver projection | 5 | 17 |
  | Python: SEC address, the individual overlap rule, parallel filing arrays, grouping | 11 | 17: custom steps, the last resort (ticket 08), since the configuration cannot state them |

- [x] Three-axis `/code-review` (Standards, Spec, GoF), findings fixed. 2026-10-02 15:43 ET
  - **GoF:** leave the structure. Each check and primitive is now named in its `match`, and an unknown one is an error rather than a fall-through.
  - **Fixed, each with a test:**
    - the deps image tag ignored the crate;
    - numbers never matched in `when`, `in_set` or `in_lookup`;
    - a broken path filter was dropped silently (paths are now checked when the contract loads);
    - a repeated required path passed;
    - dates differed from Python's `isoformat`;
    - the member limit defaulted above the artifact limit;
    - one string given as a lookup was split into characters;
    - the binding held Python's lock through a read;
    - a Python `True` from a step became `1`;
    - the facade's name clashed with the Rules database engine (now `source_engine.py`);
    - `blank_missing_token` was in Rust as well as Python (the CLI is gone, and the Rust copy is a test helper).
  - **Answered:** ticket 14's status change on this branch ticks its own merge step, as the operator asked after #796.
- [ ] ~~Stream records, so a multi-GB GLEIF Golden Copy fits in memory~~ deferred to ticket 16: the engine reads an artifact whole, within its limits. The GLEIF reader streams today (`ijson`), so 16 must add streaming to the XML and JSON readers before GLEIF moves.
- [ ] ~~A step with several inputs or the whole record (SEC address place codes)~~ deferred to ticket 17: steps take one value today.
- [ ] ~~Each custom step listed in its source's Mapping Document~~ deferred to tickets 16 and 17: no source is on the engine yet.
- [ ] ~~Codex's 41 Python research tests as CI acceptance~~ not taken: they test the Python adapters, not the engine. The engine's acceptance is the Rust suite plus the mapping above. The research file stays research.
- [ ] ~~A non-numeric value in a `number` column defers the record~~ not changed: it reads as the column's default, as `parse_thirteenf` does. A `required` check on that column catches it when a source needs that.
- [ ] PR, CI green, merge on the operator's word
