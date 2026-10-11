# Configured collections and joins

Status: in progress, Codex. Branch: codex/rust-configured-joins.
Starting point: e8b4d23a; rebase onto merged PR #920 before delivery.

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
- [ ] Qualify bounded offline Company inputs with whole census and measure computation plus full execute/verify and memory.
- [ ] Update COMBINING and responsibility map for implemented boundaries; verify commands/examples.
- [ ] Run Rust checks and applicable maintained tests, including installed bundle and real PostgreSQL acceptance where affected.
- [x] Independent Standards, Spec and GoF review; resolve all findings. Standards escaped-surrogate metadata finding corrected; independent recheck validates 2,025 code-point pairs; Spec/GoF clear; REVIEW records all axes; 2026-10-11 19:54 ET.
- [x] Fix review finding: preserve Python code points for keys, ordering, canonical tokens and empty-text handling. Public red/green regression and all 60 focused tests pass on corrected release binding; expanded 1,500 parity cases including 1,137 matching failures pass; 2026-10-11 19:54 ET.
- [ ] Rebase onto delivered merge/survivorship main; guard, commit, push, PR and all CI green.
- [ ] Merge and verify delivery, and hand off precise available interfaces/remaining Claude-owned fan-in.
