# Do the new MDM and the config parser need their own repo?

Date: 2026-09-26. Base: `1828f927` (`main` after pull request 722).

## Answer

No. Keep the old MDM, the new MDM, and the config parser in this repo. A new repository is not required to keep them from being the same design.

Pull request 722 already accepted that split inside one codebase: one versioned reading of the source bytes, then a separate MDM mapping and a separate analytical mapping ([ADR 0016](../adr/0016-independent-mdm-and-silver-mappings.md)). That record says not to add a service only to achieve the separation. A new repo would be a stronger split than the one just accepted, and the accepted record tells engineering not to move every entity pipeline as a side effect.

## What is actually coupled

| Piece | Where it lives | What it depends on outside itself |
| --- | --- | --- |
| Old MDM | `edgar_warehouse/mdm/`, 67 Python modules, not under `clean/` | Silver tables, the running graph, Forms 3/4/5 and 13F relationship derivation |
| New MDM | `edgar_warehouse/mdm/clean/`, 24 Python modules | One import of warehouse bookkeeping (`PipelineRun`, `BookkeepingStore`). It does not import the old resolvers. |
| Config parser | Rust crate `crates/source-contract`, and the Python prototype under `.scratch/source-contract/prototype/` | Neither imports MDM. The Rust reader emits columns. It does not create a Security or `ISSUED_BY`. |

The old and new designs already have a directory boundary. They share a package name and a deployment image. That is the coupling a new repo would cut, and it is also how the old graph keeps running while securities mastering is specified and not yet the writer.

## Why a new repo costs more than it separates

- The config parser is the shared reader for both consumers. Moving only the new MDM leaves the parser behind. Moving the parser too makes the old silver writers and the new MDM both wait on a second repository before the Source Contract's silver coupling is amended. ADR 0016 says that amendment is still future work.
- `ISSUED_BY` for a Security needs a mastered Company or Fund Company. Company mastering is the CIK and GLEIF work in this repo. A Security repo cannot resolve the issuer without that result, or without copying it.
- The production 13F parser and the old `cusip_stub` / title-keyed Security paths still write. The securities mastering spec says not to replace that parser in the same step. A second repo does not retire them. It only hides them.
- Tests, bronze layout, and the pinned Company universe are here. A parity trial of one CUSIP cohort is a branch in this repo. A second repo makes that trial a release of two projects.

## When a split would be worth discussing again

After three things are true: the shared source-evidence publication is what both consumers read, the config parser is the only reader for the sources being mastered, and the old MDM is no longer on the write path for those identities. Until then the boundary to keep is the one already in the tree: `mdm/clean` for mastering, `crates/source-contract` for reading, and `mdm/` outside `clean/` for the old graph.
