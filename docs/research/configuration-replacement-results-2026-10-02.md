# Tested configuration replacement opportunities

> **Later (2026-10-02, mastering to-do 15):** the Rust probes became the engine's
> acceptance suite, `crates/source-contract/tests/acceptance.rs`, with each
> counterexample turned around; `config_replacement_research.rs` is gone. The
> findings below are the record of the prototype as it was.

Date: 2026-10-02. Baseline: `542a9fa04f4359bed7e097b4cb1d5fa4b89ede15`.
Branch: `codex/custom-parsing-research-20261002`.

## Decision

**Some scalar field selections can be expressed using existing configuration
primitives. No complete active custom reader or validator was proved removable
through configuration alone.** The experiments compare current implementations
against configuration candidates, including deliberately invalid inputs.

The operator's subsequent correction prioritizes the
[loader-independent Bookkeeping design](../../skills/bookkeeping/DESIGN.md).
Removing control coupling is independent of replacing parsing code. The SEC
Company scalar projection remains a separate demonstrated parsing opportunity.
Keep classification, address interpretation, array expansion, aggregation and
GLEIF validation in code until a replacement preserves their observed behavior.

## What was tested

The Python experiments call the actual loaders, adapter, rules primitives,
Company address conversion and native GLEIF reader. Experimental YAML is loaded
through the repository's canonical rules file loader. The Rust probes use the
unchanged Source Contract engine, without registering custom callbacks.

| Candidate | Demonstrated result | Recommendation |
| --- | --- | --- |
| Ten SEC Company scalar lookups | Four fixtures match every loader output field after caller context is merged: ordinary, missing, blank and mixed scalar types. Existing `adapters.value` preserves these values. | Move literal paths into configuration with a generic Silver projection consumer. That wiring does not exist today; this is a bounded partial replacement. |
| Use MDM `mapped_field` for that Silver projection | A whitespace-only name is preserved by the loader but becomes null in the MDM adapter. | Do not substitute this API directly. Preserve the Silver blank-value contract. |
| GLEIF Level 1 mapping | Two fixtures match complete assertions, including assertion IDs and provenance; optional and repeated address components are exercised. | Keep using configured final projection. This does not justify removing the native interpretation gates. |
| GLEIF relationship raw paths | ACTIVE and INACTIVE fixtures with one dictionary period and canonical UTC dates match complete assertions. | Literal field paths are candidates for configuration inside the validated reader. Preserve period selection and date normalization. |
| SEC individual classification by configured overlap rules | Five known-form fixtures match. An ownership form plus an unknown form is incorrectly admitted as Person. A proposed `values_subset@1` primitive is absent. | Keep the current gate. A new versioned subset primitive would be implementation work requiring independent tests. |
| SEC address as plain configured components | Three fixtures differ: US state, foreign country code and foreign state-or-country code. Country/region interpretation is lost. | Keep place-code conversion; raw path selection alone is insufficient. |
| SEC parallel filing arrays | Loader emits two accessions with null for a missing second form. Existing path mapping cannot perform indexed expansion; `each` is rejected. | Keep array expansion and tolerant missing-element behavior. |
| Company grouping, ordering and distinct selection | Proposed mapping operators are rejected; Rust also rejects `group_by`. | Keep Company preparation. A future aggregation vocabulary needs separate design and verification. |
| Rust configured GLEIF XML projection | Both readers match the same six scalar columns on two ordinary records, against a shared golden file. Rust additionally projects language. | Useful prototype for flat projection; not a replacement for the authenticated native reader. |

Python source: [executable comparisons](experiments/custom-parsing/test_python_candidates.py)
and [candidate YAML](experiments/custom-parsing/python-candidates.yaml).
Rust source: [executable probes](../../crates/source-contract/tests/config_replacement_research.rs)
and [fixture, grammar and detailed results](experiments/custom-parsing/rust/README.md).

## Counterexamples that block complete replacement

### GLEIF interpretation

Direct Level 1 normalization admits records that the existing reader defers
because they are outside approved Company scope or marked deleted. Invalid
categories also change the failure reason. LEI checksum rejection is already
shared by the configured format implementation; that existing shared validation
does not supply the other source gates.

Direct relationship mapping loses six independently tested deferral contracts:
non-LEI endpoint type, excluded endpoint scope, deletion, multiple relationship
periods, INACTIVE without an end, and a reversed interval. It also changes valid
outputs and assertion IDs for a singleton period list and an offset date that
the existing reader normalizes to UTC.

These are observed counterexamples to the tested mapping, not a claim that no
future configuration language could express the requirements.

### Native XML and the Rust prototype

The same ordinary two-record XML fixture is decoded by both implementations and
compared to [one golden projection](experiments/custom-parsing/rust_scalar_expected.json).
Python preserves a valid CDATA legal name; Rust returns null. Namespace-qualified
language attributes have different intermediate representations.

Seven shared mutations demonstrate rejection differences: wrong root, malformed
XML, wrong namespace, a DTD declaration, missing header, incorrect record count
and duplicate header count. Python raises `Conflict`; Rust returns an empty
success or projects rows. Rust does reject a duplicate projected scalar, but
that does not establish validation of unprojected structure.

Rust also projects deliberately invalid domain scalar values, lacks JSON
reading, and fails a named custom step without its code callback. The combined
invalid-domain Rust probe is not an independent proof about each mutation's
Python handling; Python's separate JSON-record tests establish deletion and
scope behavior. ZIP bounds, hash verification, complete native evidence and
publication checks remain additional reader responsibilities.

## Verification

Verified locally on 2026-10-02:

- Python: **41 passed, 0 failed, 0 skipped**, 8.69 seconds; JUnit confirms counts.
- Rust: **13 passed, 0 failed**, 0.01 seconds of execution after 4.70 seconds of
  incremental compilation.
- Total: **54 passing experiment cases**, including tests that deliberately
  prove incompatibility. This is not a count of equivalent replacements.

PR preparation rerun after merging main `4e51a84f` at 10:20 ET: Python
**41 passed** in 5.58 seconds; Rust **13 passed** in 0.02 seconds after 0.21
seconds of incremental compilation. Results and recommendations are unchanged.

Reproduce from the research worktree root with dependencies installed:

```bash
uv sync --frozen --extra s3 --extra mdm
uv run pytest docs/research/experiments/custom-parsing/test_python_candidates.py -q --tb=short
cargo test --locked --manifest-path crates/source-contract/Cargo.toml \
  --test config_replacement_research
```

The recorded Python run reused the primary checkout's existing environment
read-only and supplied cached `ijson` plus this worktree through `PYTHONPATH`:

```bash
PYTHONPATH=/Users/aneenaananth/projects/edgartools-platform-custom-parsing-research-20261002:/Users/aneenaananth/edgar-local-tmp/uv-cache/archive-v0/r8CThKoY3oaHOLeS \
UV_CACHE_DIR=/private/tmp/custom-parsing-uv-cache \
uv run --no-project /Users/aneenaananth/projects/edgartools-platform/.venv/bin/python \
  -m pytest docs/research/experiments/custom-parsing/test_python_candidates.py \
  -q --tb=short --junitxml=/private/tmp/custom-parsing-python-results.xml
```

This path records the execution environment, not a portable dependency setup.
Fixtures are synthetic and bounded. No SEC requests, production sampling,
Rules registration/approval, database migration, deployment, full CI gate or
CI performance comparison was performed. Production code, approved rules and
existing tests were unchanged.

## Proposed next change

For control architecture, implement the task protocol in the linked Bookkeeping
design first. The following list describes a separate parsing refactor; it is
not a prerequisite for that decoupling. Codex owns follow-up work.

1. Add a small generic Silver scalar projection consumer using the existing
   path traversal behavior. Put the ten SEC Company paths in a versioned,
   validated contract and preserve CIK/run/raw-object/load-mode context.
2. Retain the current classification and other five loader implementations.
   Extend the comparison to supported real input shapes before retiring the
   ten inline lookups. Run affected Silver/Company and architecture tests.
3. Consider GLEIF relationship path configuration only inside the reader that
   retains scope, deletion, period and date gates. Do not route raw native
   records directly into the tested candidate mapping.

The GoF review inspected relevant source and Git history before the experiments.
Existing function registries provide the needed seam; no new class hierarchy
or design pattern was justified. These are recommendations, not completed
runtime integrations.

See the [original inventory](custom-parsing-inventory-2026-10-02.md) for caller
evidence and areas outside the experimental scope, including Name Census and
retained helpers without production callers.
