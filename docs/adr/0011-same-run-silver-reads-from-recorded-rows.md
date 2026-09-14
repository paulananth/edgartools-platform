# Same-run silver reads come from the run's own recorded rows

Filings, filing attachments and raw objects are written landing-only, but the warehouse run
that writes them reads them straight back: daily candidate seeding, configured-form selection,
artifact capture, parsers, release evidence and text extraction all look up rows this same run
just wrote. Landing rows are not queryable as silver until the dbt collapse runs, so those
lookups are answered by an in-run lookup inside `SilverDatabase`, filled by the same writer
call that records the row for landing (with or without a landing buffer attached). It keeps
the old upsert's per-column rule: columns the upsert never updated (a filing's `cik`, `items`,
`act`, `file_number`, `film_number`; a raw object's `fetched_at`) keep their first value in the
run, the rest take the latest write — so a multi-CIK accession staged twice still resolves to
the bronze path it resolved to before.

## Considered Options

- **Keep local DuckDB for these three tables.** Smallest change, but `duckdb` stays in the
  daily write path, so it can never leave the dependencies.
- **Write them to the bookkeeping Postgres store.** Durable across runs, but it would put source
  content into a store that holds tracking state only, commits only after publish, and adds a
  round trip per lookup inside the artifact loop.
- **Read from Snowflake silver.** Cannot see this run's rows until the landing load and dbt
  collapse have run.

## Consequences

The lookup answers only "what did this run record". Reads that were really about earlier runs
(the artifact cache hit, a `--force` repair's prior hash, `targeted-resync --scope accession`)
get nothing from it; the S3 listing is what prevents re-fetching SEC content, and anything that
genuinely needs an earlier run's row must read Snowflake silver.
