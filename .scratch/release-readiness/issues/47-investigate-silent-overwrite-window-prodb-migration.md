# 47 — Investigate whether the 2026-07-19–2026-07-28 window silently overwrote other migrated bronze objects

Type: research
Status: open
Blocked by: (none)

## Question

Ticket 44 root-caused the Apple earnings-8-K bronze collision and, as an adjacent finding, surfaced
a structural risk that wasn't itself in scope: between **2026-07-19** (the `prodb→prod` bulk `aws
s3 sync` migration, which copied in bronze content captured under the old byte-exact
`download_bytes` fetch path) and **2026-07-28** (PR #298, which added the immutable-write guard —
conditional S3 `PutObject` with `IfNoneMatch: "*"`, byte-compare on conflict), **any** re-fetch of
a migrated, pre-existing bronze object through the pipeline established by ticket 06
(2026-07-17's edgartools-only gateway, which fetches via `attachment.content` and inherits
edgartools' `.strip()`-normalizing `get_content_between_tags()`) would have silently succeeded in
**overwriting** the byte-exact migrated original with `.strip()`-normalized content — no error, no
application-level audit trail in `sec_raw_object` (S3 versioning would retain the prior version
underneath only because bucket versioning stayed enabled through the migration, per the runbook).

Apple's 45 accessions were never re-fetched during that window (their `_is_configured_parser_form`
gate never admitted Item-2.02 8-Ks until PR #299, 2026-07-29 — one day *after* the guard already
existed), which is exactly why they survived byte-exact and were caught by the immutability guard
instead of being silently corrupted. The open question is whether **other** already-registered,
already-fetched accessions — anything the bulk pipeline *did* have a reason to re-touch during
that 9-day window (e.g. any accession admitted by `_is_item_502_candidate_form`, ownership/ADV
forms, or any `targeted_resync`/repair run) — got silently downgraded from byte-exact migrated
content to `.strip()`-normalized content with zero record of it happening.

Investigate:
1. Was any `bootstrap-batch`/`load_history`/`targeted_resync`/repair command run against prod
   between 2026-07-19 and 2026-07-28 (check AWS Step Functions/ECS execution history for that
   date range) that could have re-fetched an already-migrated, already-registered accession?
2. For any such run found, can the affected accessions be identified (cross-referencing
   `sec_raw_object`/`sec_filing_attachment` `updated_at`/`fetched_at` timestamps against the
   2026-07-19 migration window)?
3. Is S3 object-version history still available on the canonical bronze bucket for any candidate
   object (versioning was enabled per the runbook) to directly confirm whether a version
   transition happened in that window, and if so, whether the byte content actually changed
   (not just metadata)?
4. If confirmed instances are found: is the practical impact material (the known difference is a
   single trailing-newline byte outside any parsed content) or could other, more consequential
   normalization differences exist elsewhere in edgartools' `attachment.content` path beyond the
   one already found in ticket 44?

This is a research ticket — read-only investigation (S3 version listings, execution history,
timestamp cross-referencing). No repair action in scope here; if a real, material corruption
instance is found, spin off a dedicated repair-decision ticket mirroring ticket 46's shape.
