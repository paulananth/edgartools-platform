# Research P2: repeated whole-run validation

Status: research complete; runtime implementation is outside this ticket.

Scope: explain how to remove repeated full-run scans from Bookkeeping's task
protocol while retaining immutable work, generated children, lease fencing,
independent verification and recovery. Source baseline: main `f9e89470`.

- [x] Inspect current control paths, SQL ownership and existing acceptance coverage — source/history review and 12 focused PostgreSQL 16 cases passed; 2026-10-13 19:49 ET.
- [x] Research primary PostgreSQL sources and compare viable designs — official docs cited, three alternatives compared in the research note; 2026-10-13 19:49 ET.
- [x] Reproduce query growth and artifact reads on disposable PostgreSQL 16 — 10/100/1,000-unit observations recorded in MEASUREMENTS.json and checked; 2026-10-13 19:49 ET.
- [x] Specify the proposed per-unit validation flow, generated-work integrity and recovery gates — exact method/write-path mapping and detection-timing tradeoff documented; 2026-10-13 19:49 ET.
- [x] Verify the research note, references and ownership guard; explain the recommendation — two local links and three observation records validated, overlap guard passed for three files, explanation documented in the note; 2026-10-13 19:49 ET.

Research note: `docs/research/bookkeeping-per-unit-validation-2026-10-13.md`.
