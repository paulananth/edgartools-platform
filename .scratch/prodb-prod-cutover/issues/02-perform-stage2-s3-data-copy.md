# 02 — Perform Stage 2 S3 data copy: prodb → canonical buckets

**What to build:** Actually execute Stage 2 ("S3 preservation") of
`docs/prodb-to-prod-promotion.md`: copy real data from
`edgartools-prodb-bronze` (~41GB and growing), `edgartools-prodb-warehouse`
(~263GB), and `edgartools-prodb-snowflake-export` (currently empty — see
Ticket 01 findings) into their canonical `-690839588395` counterparts.
Ticket 01's verification found this was assumed already partially done and
is not — all three canonical buckets are empty. This ticket is the actual
data-movement work everything after it depends on.

**Blocked by:** 01 — Verify canonical S3 bucket is populated and
cutover-ready (done; established this ticket is needed)

**Status:** DEFERRED (2026-07-18) — user decision: hold the entire
prodb-prod-cutover set until Ticket 20 (required relationship production
bulk-load) reaches a terminal PASS/GO disposition. Rationale: Ticket 20 is
actively writing to `prodb-bronze`/`prodb-warehouse` right now, so any data
copy started before it finishes would immediately need a repeat pass, and
committing to a cutover mechanism while the live write volume is still
changing is premature. Do not start this ticket (or 03-06, which are
transitively blocked by it) until Ticket 20 closes. Re-check Ticket 20's
disposition in `.scratch/release-readiness/issues/20-...md` before
resuming.

- [ ] Copy mechanism is chosen deliberately (`aws s3 sync`/`cp --recursive`
      for a one-time snapshot vs. S3 Batch Replication for an ongoing mirror)
      and the choice is justified given `prodb-bronze`/`prodb-warehouse` are
      **actively being written to right now** by live ingestion (Ticket 20's
      bulk-load and any future daily/incremental runs) — a naive one-time
      `sync` will be stale the moment it finishes unless paired with a
      defined watermark or repeated before cutover
- [ ] Copy preserves object keys/prefixes exactly (no path rewriting), so
      downstream code that references `warehouse/bronze/...`-style keys
      works unmodified against the canonical bucket
- [ ] Post-copy verification compares object count and total size between
      source and destination per bucket (bronze, warehouse, snowflake-export)
      and reports match/mismatch
- [ ] Old `prodb` buckets are read-only for this ticket — nothing is deleted
      or mutated on the source side
- [ ] Cost/time estimate for the copy (data volume × S3 transfer pricing,
      expected duration) is documented before running it, given the volume
      involved (~300GB+ today, growing)
- [ ] Findings/copy completion state feeds Ticket 03's "additive IAM grant"
      step with an actual populated bucket to grant access to
