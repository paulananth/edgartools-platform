# resolve_funds_bulk dedup key unstable once adviser resolves later than the fund

Status: open (confirmed root cause, not fixed)

## Symptom

Stage 17's AWS MDM E2E test (`bash infra/scripts/run-aws-mdm-e2e.sh --env prod
--mdm-run-limit 5 --graph-limit 100`) ran `mdm run --entity-type all --limit 5`
against a Fargate task, which crashed:

```
sqlalchemy.exc.IntegrityError: (psycopg2.errors.UniqueViolation) duplicate
key value violates unique constraint "mdm_entity_pkey"
DETAIL: Key (entity_id)=(73d5222d-95fb-5a06-9b84-4b84dfa06c41) already exists.
[SQL: INSERT INTO mdm_entity ... resolution_method='adviser_name_dedup' ...]
```

This is a real code bug in `edgar_warehouse/mdm/adv_bulk.py::resolve_funds_bulk`,
not an infra/grants issue -- confirmed via a discriminating query run against
the live MDM Postgres store (Snowflake-hosted, `edgartools-prod/mdm/postgres_dsn`
secret) for the colliding `entity_id`:

```
{'entity_id': UUID('73d5222d-95fb-5a06-9b84-4b84dfa06c41'),
 'resolution_method': 'adviser_name_dedup',
 'private_fund_id': None,
 'adviser_entity_id': None,
 'canonical_name': 'Csf Private'}
```

## Confirmed mechanism

`resolve_funds_bulk` (`edgar_warehouse/mdm/adv_bulk.py:295`) generates a fund's
`entity_id` deterministically from the **source row's own identity**
(`pfid:<private_fund_id>` if present, else `accession:<accession_number>:
<fund_index>`) -- this does NOT depend on the fund's adviser.

Separately, it decides whether a fund **already exists** (to avoid
re-inserting) via a *different* key: `by_pfid.get(pfid)` when a pfid is
present, else `by_adviser_name.get((adviser_entity_id, name))` as a fallback.
`adviser_entity_id` here is resolved fresh each run from currently-committed
`MdmAdviser`/`MdmSourceRef` state (`adviser_by_crd` / `adviser_by_accession`,
both built at the top of `resolve_funds_bulk` from a live query, not from
this run's own fund-processing loop).

For a fund whose adviser was **not yet resolvable** at the time the fund was
first inserted (a real, valid state -- ADV filings can list private funds
whose adviser identity hasn't independently landed in `MdmAdviser`/
`MdmSourceRef` yet), the fund gets stored with `adviser_entity_id = NULL`,
dedup key `(None, canonical_name)`.

Once that adviser is later resolved (by any subsequent `mdm run`, at any
scope -- this is not specific to `--limit`), `adviser_by_accession`/
`adviser_by_crd` will resolve a real, non-null `adviser_entity_id` for that
same fund row on the next pass. The dedup lookup then queries
`by_adviser_name.get((<real_adviser_id>, name))`, which misses (the stored
row is keyed under `(None, name)`), so `fund` resolves to `None` -- the code
takes the "new fund" branch, recomputes the exact same `entity_id` (since
entity_id generation doesn't depend on adviser at all), and attempts to
INSERT a row that already exists under that primary key. Crash.

**This is not limited to the E2E harness's `--limit 5` smoke slice.** Any
future `mdm run` (full-universe or scoped) that reprocesses a fund whose
adviser resolved *after* the fund's first insert will hit the identical
crash. Given ADV filings can list funds and their adviser in the same or
different accessions/timing, this is a standing landmine for
`daily_incremental`/any future full re-run of `mdm run`, not just this
smoke test.

## Why not patched in this session

Per user decision + advisor consult: this surfaced from an E2E smoke-test
invocation (`--limit 5`), not from the unlimited `mdm_run` that already
succeeded today (`mdm-run-perf-measure-1786282750`, 09:39-10:01, which is
what `verify-graph` confirmed at exact parity: 223,466 nodes / 586,768
edges). No production path currently exercises this failure. A blind
`ON CONFLICT DO NOTHING` patch to `_execute_insert_chunks` would silently
convert "we failed to recognize an existing entity" into "we skipped a
write" across all 5 chunked inserts in both `resolve_advisers_bulk` and
`resolve_funds_bulk`, and could mask a genuinely different bug (e.g. an
orphaned `mdm_entity` row with no `mdm_fund` row) the next time this fires.
Filed as a root-caused ticket instead of a blind mid-cutover patch.

## Fix options for whoever picks this up

- Make the "does this fund already exist" check keyed off the same
  deterministic identity used for `entity_id` generation (pfid, else
  accession+fund_index) rather than `(adviser_entity_id, name)` -- this
  preserves idempotency but may weaken the `adviser_name_dedup` fallback's
  original cross-accession consolidation intent (merging different filings
  of the same conceptual fund via adviser+name when no pfid exists); needs
  a design decision, not a blind swap.
- Alternatively, look up existing funds by `entity_id` first (cheap, exact),
  and only fall back to `(adviser_entity_id, name)` fuzzy matching for
  genuinely new source rows -- this keeps the fuzzy-match intent for new
  data while making repeat-processing of the same row always idempotent.
- Whichever approach: needs a regression test that inserts a fund with
  `adviser_entity_id=NULL`, then resolves its adviser, then re-runs
  `resolve_funds_bulk` over the same source row and asserts no crash /
  no duplicate entity.
