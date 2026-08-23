# 29 — Deploy the gated acquisition path to prod and dry-run it

**What to build:** Take the gated acquisition path (Tickets 13–19: Command
registration, the fenced ledger, the capture Facade, SEC-change-discovery
driving, retry-safety, ordered Logical Source Revisions, and the
filing-to-Silver acceptance seam) from "merged to `main`, verified locally
against ephemeral Postgres" to "live in prod and observed processing a real
diff end-to-end" — for the one source family already wired through it
(`filing_artifact`). Not a rebuild of anything already decided; this is the
first real deployment of code this map already produced.

**Blocked by:** 18 — Materialize ordered logical source revisions; 19 —
Complete the filing-to-Silver acceptance seam

**Status:** ready-for-agent

- [ ] `013_acquisition_ledger.sql` (and its widened `finalize_source_fetch`
  signature from Ticket 17) is applied to prod's MDM Postgres via the
  standard `mdm migrate` path — not ad hoc — and confirmed live (no
  `UndefinedColumn`/`UndefinedTable` on a real query), following the
  lesson in CLAUDE.md's "MDM Postgres migration-011 schema drift" incident:
  verify against the *current*, non-orphaned state machine, not a stale one.
- [ ] Warehouse and MDM images are rebuilt from current `main` and pushed to
  ECR (per CLAUDE.md's image-rebuild table — this path touches both
  `edgar_warehouse/acquisition/**` and, if `mdm/**` changed since the last
  prod image, that role too) and deployed via `deploy-aws-application.sh
  --env prod`.
- [ ] A real `drive-filing-discovery-for-date` (or the Command-registration
  seam's equivalent entry point) runs against prod for a bounded, small
  date/CIK scope — not the full universe — and is observed producing: a
  Fetch Decision per candidate, a verified Bronze capture, a materialized
  Logical Source Revision, and a Silver acceptance outcome, traceable
  end-to-end via the ledger's own status/observation-position reads.
  Chosen scope is small enough to inspect every row by hand.
  <!-- decision: which command is the real prod entry point once Command
       registration expands, and what the dry-run's exact bounded scope
       is, are resolved during this ticket, not pre-decided here -->
- [ ] A no-op replay of the same scope is run a second time and confirmed to
  change nothing new (idempotent convergence, one of the map's acceptance
  criteria) — the first live proof of that criterion against real prod
  infrastructure rather than a test double.
- [ ] Any prod-only gap found in the process (grants, orphaned state
  machines, stale secrets — this repo's history says to expect at least
  one) is fixed via a committed, re-runnable script, not a manual one-off,
  per the standing "no state survives an account rebuild unless it's
  Terraform or a script" lesson in CLAUDE.md.
- [ ] Legacy acquisition paths for `filing_artifact` are left untouched —
  this ticket proves the new path works in prod, it does not cut traffic
  over or remove the old path (that's Ticket 27, and only after every
  source family, not just this one, proves out).
