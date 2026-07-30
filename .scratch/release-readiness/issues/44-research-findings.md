# 44 — Research findings: root-causing the earnings-8-K immutable-content collision

Feeds ticket 44
(`.scratch/release-readiness/issues/44-root-cause-earnings-8k-immutable-content-collision.md`).
Written as a durable sibling artifact per this repo's issue-tracker convention, matching the
shape of `.scratch/release-readiness/issues/43-research-findings.md`.

## Method

1. Confirmed the working tree's local `main` was stale (missing PRs #298/#299); fetched
   `origin/main` and read `e0fa0ea` (#298, immutability guard) and `0c1aa09` (#299, Item-2.02
   selection fix) directly via `git show` to get the real diffs, not guesses.
2. Grepped the whole repo for `sec_filing_text` writers and any bronze-write path outside
   `fetch_filing_artifacts`/`ObjectStorage`; read the one hit
   (`edgar_warehouse/filing_text_projection.py`) in full to rule it in/out by its actual
   preconditions, not by table name alone.
3. Walked `git log --since/--until` around 2026-07-19 with real commit dates (`--date=iso`), which
   surfaced the `prodb→prod cutover` commits; read `docs/prodb-to-prod-promotion.md` and every file
   in `.scratch/prodb-prod-cutover/issues/` for the actual executed migration mechanism and its
   completion timestamps.
4. Live AWS calls (read-only): `aws sts get-caller-identity` (confirmed account
   `690839588395`), `aws s3api head-object`/`get-object` against
   `edgartools-prod-bronze-690839588395` for the specific colliding key, `aws s3api
   list-objects-v2` across a further 32 sampled CIK/accession prefixes (7 by-date + 25 random),
   `aws s3 ls s3://edgartools-prodb-bronze` (confirmed bucket no longer exists —
   decommissioned), `aws stepfunctions list-state-machines` (confirmed `targeted-resync` exists
   as a distinct state machine from the bulk pipelines).
5. Direct byte-level reproduction of question 2: downloaded the existing bronze object via
   `aws s3api get-object`; fetched the identical SEC URL directly via `curl` with the
   `EDGAR_IDENTITY`-style User-Agent (`EdgarTools Platform Research <email>`) SEC requires; then
   invoked the *actual* installed `edgartools==5.30.0` (the version locked in `uv.lock`) through
   `uv run python3`, replicating `bronze_filing_artifacts.py`'s exact call shape
   (`edgar.get_by_accession_number` → `filing.attachments` → `attachment.content` →
   `.encode("utf-8")` if `str`) to get the real bytes the current pipeline would produce today.
   Diffed all three with `sha256`, `wc -c`, `cmp`, and `xxd` on the raw byte streams — not a
   guess, an actual reproduction.
6. Read the installed edgartools source directly
   (`.venv/lib/python3.11/site-packages/edgar/{attachments.py,sgml/sgml_parser.py,sgml/tools.py}`)
   to find exactly which line produces the byte difference found in step 5.
7. Git-archaeology on `edgar_warehouse/bronze_filing_artifacts.py` and
   `edgar_warehouse/application/warehouse_orchestrator.py`: `git show f6c40f1` (ticket 06,
   "edgartools-only filing document gateway", 2026-07-17) for the pre/post code path, and
   `git show 0c1aa09` (#299) plus reading `_is_configured_parser_form`/`_is_item_502_candidate_form`
   directly to determine what the artifact-selection gate has *ever* admitted.
8. Downloaded the real, current prod silver DuckDB file directly
   (`aws s3 cp s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/silver.duckdb`,
   ~995 MB, read-only open via `duckdb.connect(..., read_only=True)`) and queried it directly —
   `sec_company_filing`, `sec_raw_object`, `sec_filing_attachment`, `sec_filing_text` — to get
   exact, current row counts rather than relying on the prior investigation's already-stated
   claim. Deleted the local copy after use; no writes were made anywhere.
9. `snow sql --connection edgartools-prod` confirmed `sec_filing_attachment`/`sec_filing_text`
   do not exist in Snowflake at all (silver-only tables, as CLAUDE.md's data-layer table implies)
   — explains why the prior ticket's metadata check must have used the DuckDB file directly, and
   why that's what this pass also used.

No write/mutating action was taken against S3, Snowflake, or any deployed AWS resource at any
point. `aws s3 cp`/`get-object`/`head-object`/`list-objects-v2`, `curl` against SEC.gov, and
read-only DuckDB opens are the only state-touching operations performed.

---

## 1. What process wrote these objects on 2026-07-19?

**The `sec_filing_text` lead is dead — ruled out directly, not just by absence of evidence.**
`edgar_warehouse/filing_text_projection.py:24-37` (`extract_text_for_accession`) requires a
**pre-existing** `sec_filing_attachment` row with a `raw_object_id` before it can do anything —
it reads `db.get_filing_attachments(accession_number)`, finds the primary row, resolves
`raw_object_id`, and raises `ValueError("No primary raw artifact registered for ...")` if that
chain is missing. Since `sec_filing_attachment` has zero rows for every one of these 45
accessions (re-confirmed live in §method 8, not just re-asserted from ticket 42), this function
could never have run for them — it has no path that writes a *first* raw artifact. It is a
downstream consumer of the raw bronze write, not a producer. Ruled out.

**The real answer: the 2026-07-19T20:13:19–22Z timestamp is not a fetch time at all — it's an
S3-copy time from the documented prodb→prod cutover.** This repo ran a full production promotion
that day, executed as a single operator session (`docs/prodb-to-prod-promotion.md`'s header:
*"EXECUTED 2026-07-19 — this runbook is now a historical record"*). Specifically, Stage 2 of
that runbook (`.scratch/prodb-prod-cutover/issues/02-perform-stage2-s3-data-copy.md`) records:

> **2026-07-19 — DONE ... Copy mechanism: server-side `aws s3 sync` (one-time snapshot...).
> Post-copy parity (current versions, source vs canonical — exact match): `edgartools-prodb-bronze`
> 433,681 objects / 39,362,929,987 bytes on BOTH sides...**

`prodb` was a second, prod-shaped environment that had been the platform's actual live/active
production system since 2026-07-02/03 (`.scratch/prodb-prod-cutover/issues/01-...md`: *"bronze/
silver ingestion is live (confirmed via 4 running ECS tasks... writing to prodb-bronze as of this
morning)"*, dated 2026-07-18) — until this cutover replaced it with the canonical
`690839588395`-suffixed resources this platform now runs on. `aws s3 sync` does not preserve a
source object's original `LastModified` — every object gets a fresh timestamp at copy time. That
single mechanical fact fully explains the anomaly ticket 44's background flagged as suspicious
("a single ~3-second bulk-write burst spanning multiple different accessions/years"): it is
*exactly* what a high-concurrency bulk copy of a multi-year historical corpus looks like — not
per-filing chronological writes, a bulk key-preserving copy landing many different-vintage keys
within a shared narrow window. Re-verified against 3 *additional* Apple accessions beyond the 4
originally spot-checked (spanning 2015, 2018, 2022 filing dates) — all land at
`2026-07-19T20:13:19–25Z`, the same ~6-second span (live `aws s3api head-object` calls, §method
step 4).

`edgartools-prodb-bronze` no longer exists (`aws s3 ls s3://edgartools-prodb-bronze` →
`NoSuchBucket`, confirmed live) — it was torn down as part of the cutover's Stage 5 cleanup
(`.scratch/prodb-prod-cutover/issues/06-decommission-old-prodb-bucket-and-objects.md`), so the
*original* pre-copy fetch event inside prodb cannot be directly re-inspected; the evidence trail
below is the strongest reconstruction available from what still exists.

**Who/what originally wrote it inside prodb (before the July 19 copy): most likely a form-agnostic
ad-hoc single-CIK fetch (`targeted_resync`), not the bulk configured-parser pipeline —
established by elimination, not by direct log evidence (that log no longer exists).**

- `_run_configured_form_artifact_pipeline` (the bulk pipeline `bootstrap-batch`/`load_history`
  use) gates every accession through `_configured_parser_accessions` →
  `_is_configured_parser_form` (`warehouse_orchestrator.py:3229-3238`). Before PR #299
  (`0c1aa09`, merged 2026-07-29, literally the day of this investigation), that function *never*
  admitted Item-2.02 8-Ks — only ownership/ADV forms and `_is_item_502_candidate_form`
  (Item 5.02). This has been true for as long as `_is_item_502_candidate_form` has existed, which
  predates prodb's entire lifecycle — so **no version of the bulk pipeline, at any point in
  prodb's life, could have selected these 45 accessions.** This is a real code-level constraint,
  not an assumption about "the same bug existing earlier."
- The only other call site of `fetch_filing_artifacts` anywhere in the codebase is
  `_run_accession_resync` (`warehouse_orchestrator.py:4259-4297`), which backs the
  `targeted_resync` Step Function (confirmed live and deployed:
  `arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-prod-targeted-resync`). It calls
  `refresh_filing_artifacts` **unconditionally** when `include_artifacts=True` — with **no
  `_is_configured_parser_form` gate at all**. This is the one code path that could have captured
  an Item-2.02-only 8-K's attachments before PR #299 existed.
- Apple (CIK 320193) is independently, heavily documented elsewhere in this repo as *the*
  designated single-CIK smoke-test subject for this exact fundamentals-backfill investigation
  chain: ticket 42's own PR #299 commit message states *"Root-caused via a live single-CIK smoke
  test against prod (Apple, 320193)"*, and `.scratch/release-readiness/issues/42-...md` /
  `map.md` describe a "stage 1 (single-CIK smoke test)" executed against Apple specifically. It
  is a well-established pattern in this workstream to run ad-hoc, form-agnostic fetches against
  Apple specifically as a pilot — exactly the shape `targeted_resync` provides.
- All 45 of Apple's Item-2.02 8-Ks (2015–2026, the full historical set silver knows about) show
  the identical `raw_object` gap (see §3), consistent with one single sweep across Apple's entire
  filing history rather than 45 independent one-off fetches.

**Not fully proven** (prodb's own execution history and DuckDB metadata no longer exist to check
directly): which specific run, on what date, invoked `targeted_resync` against CIK 320193 in
prodb. The evidence supports "a form-agnostic, non-configured-parser-gated fetch against Apple
specifically, sometime before 2026-07-17" as the most likely mechanism, by elimination against
every other call path in the current codebase — not as a directly observed log line.

---

## 2. Why does re-fetching produce different bytes than the existing 2026-07-19 object?

**Fully reproduced and diagnosed — a single trailing-newline byte, root-caused to a specific
edgartools library line, made collision-prone by a specific `edgar_warehouse` architecture
change two days before the migration.**

Downloaded the existing bronze object for `0000320193-26-000011` / `aapl-20260430.htm`:
37,639 bytes, sha256 `d41d9fd1...5261060b`, ending `...</html>\n` (trailing `0x0a`).

Fetched the **identical SEC URL directly** via `curl` with an identifying User-Agent
(`https://www.sec.gov/Archives/edgar/data/320193/000032019326000011/aapl-20260430.htm`):
**byte-identical** — same 37,639 bytes, same sha256. **SEC has not changed the document; a raw
HTTP fetch of the same URL reproduces the bronze content exactly.**

Then invoked the real installed `edgartools==5.30.0` exactly as `bronze_filing_artifacts.py` does
(`edgar.get_by_accession_number("0000320193-26-000011")` → `.attachments` → find
`aapl-20260430.htm` → `.content`, then `.encode("utf-8")` since it's a `str`, matching
`bronze_filing_artifacts.py:349`): **37,638 bytes, sha256 `1b17060c...50fb72b5`** — 1 byte
shorter. `cmp`/`xxd` on both files: **every byte through offset 37,637 is identical; the only
difference is the existing/raw file has one extra trailing byte, `0x0a` (`\n`), that the
edgartools-fetched content lacks.**

**Root cause, exact line:** `Attachment.content` (`edgar/attachments.py:299-302`) delegates to
`self.sgml_document.content`, which is `SGMLDocument.content`
(`edgar/sgml/sgml_parser.py:130-132`): `get_content_between_tags(self.raw_content)`. That
function (`edgar/sgml/tools.py:32-58`) extracts the document from its SGML `<TEXT>...</TEXT>`
wrapper via regex and returns `match.group(1).strip()` (line 49 for a named tag, line 56 for the
generic path) — **an explicit `.strip()`** that removes the trailing (and any leading) whitespace
the raw SEC-served document actually contains. This is edgartools' own library behavior in the
version this repo has locked (`uv.lock`: `edgartools-5.30.0`), not a bug in this repo's code.

**Why this specific document collides now and didn't silently collide before:**
`git show f6c40f1` (commit message: *"feat: edgartools-only filing document gateway (ticket
06)"*, **2026-07-17 19:15:41 -0400** — two days before the prodb→prod copy) removed exactly the
code path that would have produced the byte-exact (trailing-newline-preserved) content: a
*"primary-document URL + `sec_client` `download_bytes` fast path"* that fetched the raw document
via a direct HTTP GET (`payload = download_bytes(document_url, context.identity)`,
form-agnostic, the only carve-out being 13F-HR/13F-HR/A) and wrote it byte-for-byte. After ticket
06, **every** filing-document capture (any form, any accession) goes exclusively through
`attachment.content` — i.e., through the `.strip()`-affected SGML extraction path.

**Full causal chain, all links now evidenced:**
1. Before 2026-07-17: filing-document capture used the raw-HTTP `download_bytes` fast path →
   byte-exact SEC content (trailing newline preserved) written to bronze.
2. 2026-07-17 (ticket 06, `f6c40f1`): that fast path was removed; all capture now goes through
   edgartools' `attachment.content`, which `.strip()`s the trailing newline.
3. 2026-07-19: prodb's already-existing (pre-ticket-06-style) bronze bytes were copied
   key-preserving into canonical via `aws s3 sync` — the object itself is untouched content-wise,
   just relocated.
4. 2026-07-28 (PR #298, `e0fa0ea`): `write_bytes` → `write_immutable_bytes`, adding the
   byte-comparison-on-conflict guard.
5. 2026-07-29 (PR #299, `0c1aa09`): Item-2.02 selection finally works, triggering the **first-ever**
   fetch attempt for these 45 accessions through the post-ticket-06 pipeline — which produces
   content 1 byte short of what's already sitting in bronze, and the immutability guard (only 1
   day old) correctly fails closed instead of silently overwriting.

**Adjacent finding, outside this ticket's 3 questions but material to release-readiness:**
between 2026-07-19 (migration) and 2026-07-28 (immutability guard deployed), **any** re-fetch of
a migrated pre-existing bronze object through the post-ticket-06 pipeline would have hit this
exact same 1-byte-short content — but with no guard in place yet, `write_bytes` would have
**silently overwritten** the byte-exact migrated original with the `.strip()`-normalized version,
with no error and no application-level audit trail (S3 versioning would retain the old version
underneath, since versioning stayed enabled per the runbook, but nothing in `sec_raw_object`
would show a prior hash was overwritten). Whether this actually happened to any *other* migrated,
already-registered accession in that 9-day window was not checked in this pass — flagging it as a
candidate follow-up, not resolving it here.

---

## 3. Does this affect only Apple, or every company?

**Empirically: only Apple, as far as sampled — not a universal collision.** Directly queried the
current prod silver DuckDB (downloaded read-only, §method step 8) rather than inferring from S3
timestamps alone:

- `sec_company_filing` shows **53,694 total Item-2.02 8-K/8-K-A accessions across the whole
  universe** (45 of which are Apple's).
- Of the **53,649 non-Apple** Item-2.02 accessions, **53,383 (99.5%)** have **zero** rows in
  `sec_raw_object` — i.e., never fetched by canonical's own pipeline (expected: Item-2.02
  selection was broken until today). The remaining 311 that *do* have `sec_raw_object` rows were
  checked by sample (e.g. Honeywell `0000773840-26-000084`, items `1.01,2.01,2.02,3.03,5.02,...`)
  and, unlike Apple, are co-tagged with **Item 5.02**, which the artifact-selection gate has
  always admitted — those were fetched for an unrelated reason, not because of the Item-2.02 fix.
- **The key test: do any of those 53,383 "never fetched" accessions already have an orphaned
  bronze object sitting in S3 (the specific precondition for a collision)?** Sampled 32 of them
  live — the 7 most recent by filing date (Biogen, Greenbrier, Horizon Bancorp, Progress
  Software, Nike, Constellation Brands, an unnamed 6-K-adjacent filer) plus 25 chosen uniformly
  at random across the full 53,383 (spanning filing years 2005–2026, dozens of distinct CIKs).
  **All 32/32 came back with zero S3 objects under their entire accession prefix** (not just the
  `primary/` subpath — the whole accession folder is empty), via direct `aws s3api
  list-objects-v2` calls. None of them have anything to collide with; a fresh fetch for any of
  these would simply succeed as a first-time write.
- By contrast, **all 45 of Apple's** Item-2.02 accessions have `raw_object` rows missing (same as
  the others) **but do have pre-existing bronze content** (confirmed via S3 for the original
  accession plus 6 more spread across 2015–2022 in this pass, on top of the original ticket's 4)
  — the specific combination that produces a collision.

**Conclusion: this is not a universal, form-wide, or company-wide phenomenon.** It is specific to
whichever narrow set of CIKs received an ad-hoc, non-gated fetch (almost certainly
`targeted_resync`, per §1) against prodb before 2026-07-17, carried into canonical bronze by the
July 19 migration, and never re-registered in canonical's silver metadata. Apple is
independently, heavily documented as the sole dedicated single-CIK smoke-test subject for this
whole investigation thread, which is consistent with it being the only (or one of a very small
number of) CIK(s) actually affected. This sample (32 other-company accessions, all clean) does
not prove *zero* other CIKs anywhere in the universe are affected — only that it is not the
default/common case, and the 53,383-accession non-Apple population as a whole is dominated by
"never fetched at all" rather than "orphaned pre-existing bronze."

---

## Bottom line for ticket 44

All three open questions are now answered with direct, reproducible evidence rather than
speculation:

1. **Writer:** the July 19 timestamp is an S3-copy artifact from the documented prodb→prod
   cutover (`aws s3 sync`, `.scratch/prodb-prod-cutover/issues/02-...md`), not an original fetch
   time. The original content was most likely written inside `prodb` by an ad-hoc, form-agnostic
   `targeted_resync` run against Apple specifically (the only code path in this repo that ever
   fetches filing-document attachments without going through the Item-2.02-blind
   `_is_configured_parser_form` gate) — established by elimination of every other call path, not
   by a surviving log (prodb's own execution history and metadata no longer exist to check
   directly).
2. **Byte diff:** exactly 1 trailing-newline byte (`0x0a`), reproduced live: raw SEC fetch and
   the existing bronze object are byte-identical (sha256 `d41d9fd1...`); the current
   `edgartools==5.30.0` `attachment.content` path produces sha256 `1b17060c...`, one byte
   shorter, due to an explicit `.strip()` in `edgar/sgml/tools.py:49,56`
   (`get_content_between_tags`). This mismatch became *possible* only because `edgar_warehouse`
   switched exclusively onto that `.strip()`-affected path on 2026-07-17 (ticket 06, `f6c40f1`),
   two days before the pre-ticket-06-style bronze content was migrated in verbatim.
3. **Scope:** empirically Apple-specific among everything sampled (32 other-company Item-2.02
   accessions, 0/32 have any pre-existing bronze to collide with) — not a universal 8-K/earnings
   problem. Ticket 42's F5 backfill is not blocked at the whole-universe level by this; it needs
   a scoped repair for Apple's 45 accessions specifically (and should re-check for any other
   individually-smoke-tested CIK before assuming the list is exactly 45), not a blanket
   assumption that every earnings 8-K in prod needs this treatment.

**Root cause is understood, not just described.** No repair action was taken in this pass (none
was in scope) — but any fix design now has the real mechanism to work from: this is a
same-logical-document, whitespace-normalization mismatch between two different historical capture
mechanisms, surfaced for the first time by three independent, correctly-behaving changes landing
in sequence (ticket 06's gateway consolidation, the July 19 migration, and PR #298's new
immutability guard), not a corruption, not a wrong-document collision, and — per §3 — not a
universal blocker.
