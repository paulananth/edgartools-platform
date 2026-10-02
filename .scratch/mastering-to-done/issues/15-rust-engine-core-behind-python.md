# Rust engine core behind Python

Type: task (code)
Status: open
Blocked by: 08

## Question

Build the configured source engine in Rust (`crates/source-contract`), called only from Python (ticket 08).

- **Python binding:** a PyO3 module built with maturin, plus a thin Python facade in `edgar_warehouse/rules/`. The warehouse and MDM Docker images build and install the binding.
- **Readers:** json, jsonl, xml, csv and zip, with bounded memory. XML must keep CDATA and reject malformed input, a wrong root, namespace, header or count, and a DTD.
- **Primitives** for paths, formats and checks, declared in the rules files.
- **Custom steps:** named Python callbacks the rules file declares, used only as the last resort.
- **Acceptance:** Codex's research suites (`docs/research/experiments/custom-parsing/`, `crates/source-contract/tests/config_replacement_research.rs`). Each counterexample that blocks a replacement there must now pass.

**Open design points**, settled at the start of the ticket:
- the facade's API;
- how a custom step is registered;
- how the engine reports a deferred record versus a failed one.

GoF consult first, then the three-axis review.
