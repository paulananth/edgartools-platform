# Configured collections and joins

Status: delivered and CI-qualified, Codex. Branch: codex/rust-configured-joins.
Starting point: e8b4d23a; rebased onto merged PR #920 (cd277677).
Delivered in PR #921, main 3a75cfd1. Evidence/handoff closeout follows on its own branch.

Move configured materialized source.combine grouping, scalar ordering, distinctness,
missing-match policy, nested joins and drops into the Rust engine, through the
existing Python facade. Custom code stays Python. Python retains authentication,
input and output byte bounds, EOF/partition proof, receipts, JSON encoding and
execute/verify orchestration. Database guarantees and Company/Bookkeeping fan-in
are unchanged. No new vocabulary, activation or live requests.

Keep exact types (including arbitrary integers, bool vs int, signed zero),
canonical equality, stable order, original-row keys, checks/filter validation,
raw flatten bounds, all-input/output row limits, nested copy semantics, error
precedence and no publication before complete validation. Rust retains opaque
Python payload references; no JSON round trip or per-source native code.

GoF review: source_combine history #819/#822/#827/#830/#854/#878/#911 shows growing
configured grammar and authentication, already separated behind the source engine
facade. Retain functional adapter; new classes/Strategy/Interpreter would add
indirection and migration costs without reducing a demonstrated caller cost.
The existing worker's execute/verify tests provide the characterization seam.

## Parts

- [x] Inspect ownership, live state, code/history and GoF references; choose existing facade seam. Fresh dedicated tree, guard passes on parent, raw payload/ref boundary inspected; 2026-10-11 19:39 ET.
- [x] Add a failing native/public-worker tracer, then implement configured collection and join computation. AttributeError red then four native/public regressions green; all 118 affected worker/reduction cases pass; 2026-10-11 19:46 ET.
- [x] Verify exact baseline parity across configured modes, failures, bounds, native payload identity and installed worker execute/verify. Release binding loaded; 1,500 deterministic exact comparisons including 1,100 matching failure classes/messages, no input mutations; 118 public cases pass; 2026-10-11 19:46 ET.
- [x] Qualify bounded offline Company inputs with whole census and measure computation plus full execute/verify and memory. 40 cached documents/20 worker units, 43,245-name whole census; exact receipt/table hashes, verification and lost-ack retries match; raw timing/RSS recorded in company-40.json (8m02s); 2026-10-11 20:07 ET.
- [x] Update COMBINING and responsibility map for implemented boundaries; verify commands/examples. Release documentation audit passes, unchanged grammar exercised by public and installed CI tests, doctor resolves all 131 commands; 2026-10-11 20:07 ET.
- [x] Run Rust checks and applicable maintained tests, including installed bundle and real PostgreSQL acceptance where affected. 165 Rust tests, feature typecheck, 275 architecture/Company/merge checks; local installed/PG16 suite 84 passes in 19m48s at its initial pinned fixture; final-head CI 38186218511 passes all six jobs including corrected full engine/installed bundle and real PG16 integration; 2026-10-11 20:07 ET.
- [x] Independent Standards, Spec and GoF review; resolve all findings. Standards escaped-surrogate metadata finding corrected; independent recheck validates 2,025 code-point pairs; Spec/GoF clear; REVIEW records all axes; 2026-10-11 19:54 ET.
- [x] Fix review finding: preserve Python code points for keys, ordering, canonical tokens and empty-text handling. Public red/green regression and all 60 focused tests pass on corrected release binding; expanded 1,500 parity cases including 1,137 matching failures pass; 2026-10-11 19:54 ET.
- [x] Rebase onto delivered merge/survivorship main; guard, commit, push, PR and all CI green. Dedicated branch rebased onto cd277677; guarded commits/push, PR #921 and all six checks pass at 5a823c48; 2026-10-11 20:07 ET.
- [x] Merge and verify delivery, and hand off precise available interfaces/remaining Claude-owned fan-in. PR #921 verified merged as 3a75cfd1, tree identical to reviewed 5a823c48; HANDOFF-TO-CLAUDE.md records interfaces, runtime pins and ownership; 2026-10-11 20:07 ET.
