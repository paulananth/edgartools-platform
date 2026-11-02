# 173: The 13F source is named for what it masters

Priority: 173. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 12:47 ET (operator, 2026-11-02: "Why is it called sec.thirteenf.information_table? Did we not make it meaningful", then "sec.thirteenf.securities").

Type: task. Status: resolved (2026-11-02 12:57 ET, operator: "Agreed"). Blocked by: none. Blocks: [172](172-thirteenf-securities-run-through-bookkeeping-and-the-change-journal.md).

## Question

`sec.thirteenf.information_table` is the SEC's name for the document. It does not say that the source gives the Security master its CUSIPs, names and class titles. What is it called?

Answer: `sec.thirteenf.securities` (operator's word). Its Dataset Contract, named `<source>.<kind>.vN` there (`sec.thirteenf.information_table.security.v1`), becomes `sec.thirteenf.securities.v1`, as `sec.nport.security.v2` is the source name and a version. The capture family `sec.thirteenf_infotable` is the bronze layout, not the source's name, and stays.

## Parts

- [x] GoF consult before any code (2026-11-02 12:56 ET): a rename; leave the structure
- [x] The rules folder, the `source:` name, the Dataset Contract code, the Security merge rules (the kind's source list, the identifier source list, two rules that read the source, and a new descriptive version label), the sequence, the docs, the security-master skill, the Rust contract file and the tests, with every use listed first (`.scratch` records of past runs are left) (2026-11-02 12:56 ET: 14 files plus the folder)
- [x] The Mapping Documents are regenerated (2026-11-02 12:56 ET): this source, the Security kind and, because they list the Security source order, `openfigi` and `sec.nport.security`; `test_rules_mapdoc.py` passes
- [x] Tests: 2,124 pass in `tests/mdm`, `tests/unit` and the engine contract and worker tests; 41 pass in the four integration tests that use the source; `test_rules_mapdoc.py` passes on the regenerated workbooks; the Rust contract fixture test runs in CI
- [x] What the rename costs the data: before, the shared local MDM holds no rows under the old dataset code (31 tables with a source or dataset column scanned) and the Change Journal holds no event for any `sec.thirteenf*` source (the source had no target, so nothing was ever recorded); after, nothing is registered under the new code yet. The rules digest and the dataset code change, so every file of this source is processed under the new code on its first run. Bronze receipts name the capture family, which is unchanged
- [x] Ticket 172 uses the new name (2026-11-02 12:56 ET)
- [x] Learning → skill: `security-master` names the source (2026-11-02 12:56 ET)

## Review and approval (2026-11-02 12:57 ET)

Three-axis review. GoF: leave it; four tests repeat the dataset code and a shared constant waits for a fifth. Standards: no leftover of the old name outside `.scratch` (past-run records; one old script there, `96_measure_merge.py`, would fail if reused); the SEC's own words "information table", the capture family and the `sec_thirteenf_holding` table are rightly unchanged. Spec: the Security rules `security-cusip` (2026-10-27.1) and `thirteenf-security-figi` (2026-10-26.1) keep their rule versions, since their logic is unchanged and only the source they read is renamed; the kind's version label is new (`security-2026-11-02.thirteenf-source-is-securities`) and the rules digest covers the whole file, so nothing pinned to a digest can miss the change.

Rules approval, under the standing words of 2026-10-15 ("Approved the rules always"), recorded as given on this evidence: the renamed source's rules produce the same records (the Security merge, share class, N-PORT holding and OpenFIGI tests pass unchanged apart from the code string), and the Mapping Documents equal the rules. What is approved: the Security kind reads its 13F records under the dataset `sec.thirteenf.securities.v1`. Nothing is registered under it yet; the first load under ticket 172 registers it.

The stamps on this ticket's parts were written together when it closed, not as each part finished.

