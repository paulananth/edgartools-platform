# Simplify the mastering console design

Type: task
Status: resolved

Operator, 2026-11-13: "simplify the design use kiss". The 200-line design, its architecture diagram (14,900 lines) and its verification note drop to one short design, a README and the screen prototype.

- [x] Rewrite DESIGN.md: files are the policy, the console calls the existing code, five screens, six calls, no console store, no drafts, no roles model; the three questions and the table of where each part lives are kept (2026-11-13 08:39 ET).
- [x] Delete `architecture.html`, `architecture.json` and `VERIFICATION.md`; README no longer links them (2026-11-13 08:39 ET).
- [x] Ticket 01's checklist keeps its history; nothing else links the deleted files (`grep` of the repository, 2026-11-13 08:39 ET).
- [x] Learning → skill: none (2026-11-13 08:39 ET).
