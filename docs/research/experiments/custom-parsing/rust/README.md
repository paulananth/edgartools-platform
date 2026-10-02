# Existing Rust configuration replacement experiments

These probes use the unchanged `source-contract` Rust engine from baseline
`542a9fa0`. They register **no custom function**, so a successful extraction
demonstrates an existing configured primitive rather than another custom parser.
The raw XML is synthetic and bounded to two Level 1 records, not source coverage
or deployment evidence.

## Run

From the repository root:

```bash
cargo test --locked --manifest-path crates/source-contract/Cargo.toml \
  --test config_replacement_research
```

The executable characterization tests are
[`config_replacement_research.rs`](../../../../../crates/source-contract/tests/config_replacement_research.rs).
They load [`gleif-level1.yaml`](gleif-level1.yaml) and
[`gleif-two-records.xml`](gleif-two-records.xml). Tests pin both successful
projections and observed failures/gaps; passing this suite does not mean those
gaps are acceptable for production.

Verified 2026-10-02: **13 passed, 0 failed**, 0.01 seconds of test execution
after 4.70 seconds of incremental compilation. This is the bounded research
suite only, not a CI or performance result.

## What existing configuration can do

For the ordinary namespaced XML fixture, `each`, `text`, `ordinal` and explicit
defaults project two records into scalar columns: LEI, legal name, category,
country, postcode, language and record ordinal. An absent optional postcode or
language becomes null, and an escaped `&amp;` becomes `&`. No engine extension or
registered callback was needed.

The Rust positive probe also compares all six shared scalar columns for both
records against [`rust_scalar_expected.json`](../rust_scalar_expected.json).
The Python native-decoder probe uses the same XML fixture and golden JSON.
Language is asserted separately in Rust because the intermediate attribute
namespace representations differ. This establishes the shared bounded scalar
projection explicitly; it does not establish full native-record equivalence.

**Conclusion: partial scalar-projection replacement is demonstrated. Complete
replacement of `gleif_source.inspect_archive`, `_xml_records`, `_xml_value` or
`record_evidence` is not demonstrated and is contradicted by the probes below.**
The experiment produces a flat projection, not the authenticated complete native
record, and does not reproduce ZIP bounds, hashes, member counts, native evidence
retention, LEI validity, eligible scope or domain admissibility.

## Counterexamples with the current engine

| Probe | Observed Rust behavior | Why this limits replacement |
| --- | --- | --- |
| Wrong root | Successful empty table | Native GLEIF decoder treats a wrong root as a conflict. Empty success cannot preserve rejection behavior. |
| Malformed XML | Successful empty table | Source corruption does not fail closed at this boundary. |
| Wrong namespace | Produces both rows | Namespaces are stripped; GLEIF namespace validation is absent. |
| DTD declaration without entity use | Produces both rows | Native GLEIF rejects a document type declaration. |
| Missing header / wrong record count | Produces both rows | Header and count verification are absent. |
| Duplicate unprojected header field | Produces both rows | The projection does not validate unrequested structure. |
| Duplicate projected LEI field | Error crossing a repeating group | Some cardinality errors are rejected, but this does not cover header duplicates or duplicate JSON keys. |
| Invalid LEI/category and deletion extension | Projects invalid LEI/category; ignores extension | Native interpretation's validation/defer decisions are not reproduced. |
| CDATA legal name | Null name | Existing XML reader ignores CDATA; scalar extraction is not equivalent for all valid XML text. |
| GLEIF JSON and SEC JSON parallel filing arrays | `this reader implements xml, not json` | The present reader cannot decode these source formats. |
| `group_by` expression | `primitive group_by is not implemented` | Existing configuration cannot replace Company ticker/form aggregation. |
| Named `custom` LEI step with no callback registered | `no value step lei@1` | Naming a custom step does not remove the implementation it requires. |

These are counterexamples, not suggestions to weaken the Python acceptance rules.
The parent research compares the XML fixture and mutations against Python's
existing native decoder. Language attributes also have different intermediate
representations: Rust strips attribute prefixes to `@lang`, while Python's
`lxml` representation retains expanded namespace names. Flat value projection
does not establish equality of native evidence objects.

## Design review and limits

Before adding the probes, `gof-refactor-reviewer` was applied to the crate source
and Git history. History contains the initial crate addition in `2b52b291`
(PR #719), with no later recurring branch-growth evidence. The registry of
function pointers and parsing dispatch are suitable existing seams for this
experiment. **Leave the engine unchanged**; no GoF refactor was justified.

This is an offline bounded experiment. No SEC calls, Rules approval, database
migrations, deployment or performance comparison were performed. Runtime
integration of this standalone prototype is still a separate task.
