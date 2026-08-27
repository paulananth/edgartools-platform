# 26 — Rebuild and activate a ledger epoch

**What to build:** Initialize or recover ledger authority through an explicitly
authorized Hybrid Source Baseline, continued acquisition, catch-up barrier,
complete non-serving Silver candidate, verification, and atomic activation.

**Blocked by:** 09 — Decide the cross-stage coordinator and composite watermark
contract; 10 — Decide baseline, migration, cutover, and rollback sequencing;
21 — Migrate submissions snapshots and pagination; 22 — Migrate company-facts
snapshots; 23 — Migrate reference catalogs; 24 — Migrate ADV sources; 25 — Add
conflict, repair, exclusion, and evidence-import workflows

**Status:** ready-for-agent (corrected 2026-08-27 — Ticket 10 resolved, so
every listed blocker is now satisfied). Ticket 10's own Answer narrowed this
ticket's real-world necessity: ordinary per-family cutover onto the gated
acquisition path (Tickets 21-25's own families) does **not** route through
this ticket's rebuild machinery at all — it starts capturing forward from
each family's already-trusted existing data instead. This ticket is
reserved strictly for genuine ledger loss/reinitialization, and per Ticket
10's Decision 5, no longer blocks [Ticket 27](27-contract-legacy-acquisition-bypasses.md).
Still a legitimate, real piece of disaster-recovery machinery worth
building — just off the critical path to legacy-bypass removal.

- [ ] Operator authorization fixes the reason, coverage contract, cutoff,
  deployment cohort, and new Ledger Epoch before rebuild begins.
- [ ] Each family uses verified Bronze plus complete SEC change intervals where
  sufficient, or a fresh complete SEC snapshot or bulk reconciliation where
  change capture is insufficient.
- [ ] New acquisition continues during rebuild and the catch-up barrier proves
  every required family complete through the activation high-water mark.
- [ ] The rebuilt Silver candidate remains non-serving until completeness,
  lineage, counts, digests, and publication outcomes verify successfully.
- [ ] Activation is atomic, failure preserves the old serving authority, and
  pre-epoch Bronze is not inferred into ledger authority without selection.
