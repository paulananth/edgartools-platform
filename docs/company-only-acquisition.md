# Local SEC Company acquisition

`sec.submissions.company/submissions` is the sole active acquisition feed.
The `company` Rules target captures a bounded CIK scope through fresh
Bookkeeping and Change Journal control. Other acquisition feed declarations
and old acquisition command registrations are retired. GLEIF's MDM mapping
contracts and historical audit stores remain available.

Prepare an immutable input manifest with:

```bash
uv run --extra mdm --extra s3 edgar-warehouse bookkeeping prepare \
  --source sec.submissions.company --feed submissions \
  --scope-manifest <URI> --scope-sha256 <SHA256> \
  --support-manifest <URI> --support-sha256 <SHA256> \
  --output-root <unique-run-file-URI>
```

The scope JSON is `{"version":1,"ciks":["0000320193"],"prior":{}}`.
The scope is limited to 1,000 distinct CIKs; each main submission may declare
at most 124 pagination files so the complete source evidence stays within the
Journal's bounded reference inventory.
`prior` may pin a verified prior capture by CIK for conditional requests.
For a later source revision, `revisions` may pin each CIK's last committed
`revision`, `position`, and prior immutable source revision receipt. The
first revision defaults to revision `0`, position `-1`, and no predecessor.
Use a new output root and scope document for each new root run; retained
outputs are immutable.
The support JSON pins a `ticker_manifest` reference and `name_census` and
`bindings` maps from each CIK to fixture references, plus a timezone-aware
`as_of` timestamp for the MDM bundle. Name Census fixtures
carry local name counts; the Company stage checks their SEC names against
landed rows. Each reviewed binding fixture names an entity UUID, actor,
reason and time. Place the ticker fixture under the run's `landing/` root so
the existing Company bundle adapter can read it with the Silver manifest.
This qualifies only these local inputs; it does not approve
future upstream ticker, GLEIF or binding supply.

After the exact Rules version has separate proof, approval, activation and
MDM registration in isolated PostgreSQL 16 stores, submit:

```bash
uv run --extra mdm --extra s3 edgar-warehouse rules run \
  --source sec.submissions.company --feed submissions --target company \
  --input-manifest <PREPARED_URI> --input-sha256 <PREPARED_SHA256> --limit 100
```

The returned Bookkeeping run ID is the recovery handle. Use `bookkeeping
resume <run-id>` for work and `change-journal recover bookkeeping <run-id>`
for committed undelivered Journal intent. The target verifies generated
pagination, immutable Silver Parquet bytes and business keys, source producer
inventories, MDM commit effects and local publication readback. This route is
local qualification only; it performs no AWS deployment or merge.

## Local acceptance

`tests/integration/test_company_only_postgres.py` uses restricted PostgreSQL
16 roles and two Company fixtures. It verifies a conditional 304, two page
captures (including an empty page), exact landed filing keys, two MDM entity
projections, all Journal receipts, zero pending deliveries and publication
backlog, and refusal to resume after destination Parquet corruption.
`test_generated_bookkeeping_postgres.py` verifies atomic child insertion,
idempotent replay, changed-child rejection, stale lease rejection and unsealed
root blocking. The configured Bookkeeping and Change Journal PostgreSQL suites
exercise approval, lease takeover, checkpoint contention, lost
acknowledgements, Journal outage, duplicate delivery, version drift and
evidence corruption. These fixtures do not qualify AWS promotion or the
future upstream supply of ticker and Name Census artifacts.
