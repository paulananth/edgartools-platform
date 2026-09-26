# Grok takeover: heavy-parse-rules

Scope: preserve the authorized Grok work, verify it, and check it in on `codex/heavy-parse-rules`. No deployment, matching-rule activation, database cleanup, or merge is included.

Recovery: original Grok worktrees are untouched. Heads, tracked patch and non-build untracked files are backed up at `~/.local/share/edgartools/branch-recovery/grok-takeover-20260926T171709Z/` with SHA-256 file manifest and Git bundle. Rust `target/` artifacts remain in the original worktree and are excluded from check-in.

- [x] Capture the source branch and unfinished files — bundle, patch and file manifest verified (2026-09-26 13:18 ET).
- [x] Transfer into a dedicated Codex branch/worktree based on `origin/main` `082d9461` — branch and status verified (2026-09-26 13:18 ET).
- [x] Review source and git history with GoF — no new pattern warranted; correct portable paths/limits, root-name regression and silent Rust parse errors; separate measurement from production acceptance (2026-09-26 13:30 ET).
- [x] Verify — 4 prototype tests, 6 lookup checks, 3 Rust tests; 10/10 real cached files and 286,134 rows match the ten compared fields with zero rejects/type errors; all 1,000 cached sizes verified (2026-09-26 13:36 ET).
- [x] Review staged source/evidence — no binaries, private keys, AWS credentials or DSNs; Rust `target/` ignored and `git diff --cached --check` passes (2026-09-26 13:36 ET).
- [ ] Commit and push the Codex branch, then verify the remote hash and clean worktree.

## Review

GoF review read the prototype reader and production parser boundary plus the Source Contract prototype/cold-onboarding history. The existing format dispatcher is an external-input boundary; a Strategy hierarchy would add indirection without demonstrated recurring cost. Keep the explicit reader and small custom value step.

Corrections for check-in: retain both expanded and local XML root matching; portable pin/cache parameters; bounded positive sample sizes; cache size checks; fail comparison on rejects/type errors; portable RSS units; ignore Rust build output; return an error for malformed/truncated XML. Rust unit checks cover namespace/entity text, malformed XML and missing tokens. The Rust program remains a timing fold, not a row-equivalent production reader.

The original inventory/download and full 100/1,000 reports are preserved as historical Grok evidence. Raw full-run output files were not handed over. See the comparison report's added evidence limits. Neither the column-selecting contract nor Rust fold implements ADR 0016's lossless shared parsed-record layer. No source rules or production parsers were activated.


## Verification

Fresh evidence: [receipt](evidence/heavy-parse-2026-09-26.json), including tool versions, source fingerprints, pin SHA-256 and the ten cached artifacts' SHA-256 values.

- Prototype namespace and named-case regression tests: **4 passed**.
- Existing as-of lookup self-test: **6 passed**.
- Rust tests: **3 passed**, `cargo fmt --check` passes.
- Python limit checks: 0 and 1,001 rejected before cache reads.
- Inventory: 17,259 JSONL records; 100/1,000 pin membership and all 1,000 cached sizes verified.
- Fresh bounded Python comparison: **10/10 files; 286,134 rows on each side; zero empty, mismatched, rejected or type-error records**. Ten selected fields only; period/unit policy, security classification and writer behavior are outside this comparison.
- Fresh Rust fold: 10 files, 286,134 rows, 20.254 s parsing / 0.200 s reading. This proves a runnable timing fold and matching row counts, not field parity.

The bounded Python run took approximately 12 minutes including native-library startup; measured rules processing was 243.46 s and production-parser processing 296.58 s. These are check-in measurements under the current local load, not a controlled performance qualification. The original full-size reports were not rerun. No production publication, database or parser cutover was exercised.

```bash
uv run --extra mdm --extra s3 --with ruamel.yaml --with jsonschema pytest .scratch/source-contract/prototype/engine/test_thirteenf.py -q
uv run --extra mdm --extra s3 --with ruamel.yaml --with jsonschema python .scratch/source-contract/prototype/engine/selftest.py
uv run --extra mdm --extra s3 --with ruamel.yaml --with jsonschema python .scratch/source-contract/prototype/compare_thirteenf.py 10
cargo fmt --check --manifest-path .scratch/heavy-parse-rust/Cargo.toml
cargo test --locked --manifest-path .scratch/heavy-parse-rust/Cargo.toml
cargo run --release --locked --manifest-path .scratch/heavy-parse-rust/Cargo.toml -- 10
```
