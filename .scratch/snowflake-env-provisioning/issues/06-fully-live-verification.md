# Decide what "fully live" is verified by

Type: grilling
Status: resolved

## Question

The map's Destination requires the script to stand up a "fully independent,
prod-shaped environment" — but nothing yet defines what confirms that
claim once all four domains (source-native-pull, gold, MDM, Neo4j) are
provisioned. Ticket 05's answer surfaced that `go-live.sh`'s existing
13-stage sequence already ends in what look like verification steps:

- Stage 12 ("MDM + graph: connectivity, migrations, sync, verification") —
  `mdm check-connectivity`, `mdm migrate`, `mdm seed-universe`, `mdm run`,
  `mdm sync-graph`, `mdm verify-graph`
- Stage 13 ("MDM + graph: AWS MDM E2E/status checks") — `run-aws-mdm-e2e.sh
  --status-only` then a bounded E2E run
- Stage 14 ("Data: bounded smoke only") — bounded `seed-universe` +
  `bootstrap-next` against real SEC data

Resolve: do these three existing stages already constitute "fully live"
verification for a brand-new environment, or is something missing —
e.g. confirmation that gold's dynamic tables actually contain rows (not
just that they exist/compile), that the dashboard is reachable, or that
the Snowflake Postgres MDM instance is actually queryable end-to-end? If
something's missing, what closes the gap, and does it become a new stage
in `go-live.sh`'s sequence (per Ticket 05) or a standalone check run once
at the end?

## Answer

**Traced, not assumed:** MDM has a real automated check
(`mdm check-connectivity`, `edgar_warehouse/mdm/cli.py:1300`), the graph has
`mdm verify-graph`'s strict SQL parity check, AWS has
`run-aws-mdm-e2e.sh`. Gold has none — stage 11 (`go-live.sh:753`) only
`echo`s "verify row counts in EDGARTOOLS_GOLD before treating gold as
current" to the operator; nothing fails the stage or the wizard if gold is
actually empty. That's the one real gap across all four domains.

**Scope: automated gold row-count check only, no dashboard reachability
check.** Streamlit-in-Snowflake apps run behind Snowflake session auth, so
a meaningful reachability check would mean solving that auth problem just
for this one check — disproportionate scope next to what actually matters
for "fully live": the underlying gold data being correct. If gold's tables
are populated and MDM/graph/AWS verification all pass, the dashboard
(a thin read layer over gold) is live by construction.

**Shape: a standalone CLI command, called from a new final go-live.sh
stage** — mirrors the existing `mdm verify-graph` precedent exactly (stage
12 already wraps a standalone command rather than inlining SQL into the
stage's bash block). A new `edgar-warehouse gold verify-live`-style command
(exact name TBD at implementation time) queries row counts across
`EDGARTOOLS_GOLD`'s dynamic tables and fails (non-zero exit) if any
expected table is empty. This makes the check independently runnable —
testable in isolation, and reusable later as a standalone post-deploy
health check outside the wizard, not just inside `go-live.sh`.

**Where it lands in the sequence:** appended as a new final stage after
existing stage 14 ("Data: bounded smoke only"), since it needs stage 14's
freshly-fetched real data (via stage 11's gold-refresh or a subsequent one)
to have actually landed in gold before row counts are meaningful — this
is the true end of the "fully live" chain, closing the loop the map's
Destination opened.

**Not built here** — per wayfinder's plan-don't-do default, this records
the decision; implementing the CLI command and wiring the new go-live.sh
stage is work for whoever executes this map's destination.
