# 8-K Item 5.02 employment-event Person pipeline, traced from code

Ticket: [13](../issues/13-trace-8k-employment-event-person-pipeline.md). Run 2026-09-19. Code-only.
No Snowflake, AWS or network query was made; every claim is `path:line` in
this worktree (branch `claude/person-consumer-contract`), except the Clean MDM
target, read with `git show origin/codex/clean-mdm-integration:<path>`.

## What was read

- Parser: `edgar_warehouse/parsers/item_502.py` (649 lines, whole file).
- Fetch/parse stages: `edgar_warehouse/application/warehouse_orchestrator.py`
  (lines 200-211, 3440-3846, 5307-5492), `edgar_warehouse/application/workflows/fundamentals_ingest.py`
  (lines 113-334), `edgar_warehouse/application/commands/bootstrap_fundamentals.py`
  (160-180), `edgar_warehouse/infrastructure/silver_once.py`,
  `infra/scripts/deploy-aws-application.sh` (2787-2830, 3759-3790).
- Silver: `edgar_warehouse/silver_schema.py` (234-246, 579-587),
  `edgar_warehouse/silver_landing_store.py` (379-446, 475-481, 581-584),
  `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql` (359-374),
  `infra/snowflake/dbt/edgartools_gold/models/silver/sec_employment_event.sql`,
  `infra/snowflake/dbt/edgartools_gold/macros/silver_not_retired.sql`,
  `edgar_warehouse/mdm_entity_backfill.py` (106-151).
- Legacy MDM: `edgar_warehouse/mdm/pipeline.py` (141-195, 1700-1738,
  3247-3277, 3496-3596, 3743-4068), `edgar_warehouse/mdm/resolvers/person.py`
  (whole), `edgar_warehouse/mdm/rules.py` (140-165),
  `edgar_warehouse/mdm/database.py` (296-318, 679-697), `edgar_warehouse/mdm/coverage.py` (414-419).
- Downstream: `edgar_warehouse/mdm/snowflake_graph.py` (20-75, 1599-1602),
  `edgar_warehouse/serving/dashboard_workflows.py` (232-246),
  `edgar_warehouse/serving/subject_bundle_read.py` (40-42, 219-238, 393-400),
  `edgar_warehouse/serving/source_dimensional_export.py` (348-367),
  `infra/snowflake/sql/bootstrap/01_source_stage.sql` (446-458),
  `infra/snowflake/dbt/edgartools_gold/models/sources.yml` (59, 129),
  `infra/snowflake/dbt/edgartools_gold/models/gold/executive_records.sql` (36),
  `edgar_warehouse/mdm/clean/relationships.py` (11-16), `docs/adr/0008-name-relationship-closing-patterns.md` (10).
- Tests: `tests/unit/test_item_502_parser.py` (401 lines, whole),
  `tests/unit/test_item_502_branch_a_parse.py`, `tests/unit/test_item_502_spacy_runtime_deps.py`,
  `tests/mdm/test_pipeline_relationships.py` (867-1060, 2974-3060).
- Clean MDM target: `docs/specs/clean-mdm/pipeline-inventory.md` (rows 23, 26)
  and `docs/specs/clean-mdm/domain-model.md` (12, 25-30, 68, 84-95) on
  `origin/codex/clean-mdm-integration`, never checked out or edited.

## Findings

### Area 1 — source form and fetch

**F1 — Source is 8-K / 8-K/A, selected by declared items, with blank items
treated as a candidate.** `_is_item_502_candidate_form` returns True for
`8-K`/`8-K/A` when `items` is empty *or* matches `5.02`
(`warehouse_orchestrator.py:3636-3644`). The docstring is explicit: "True
for 8-K/8-K/A with Item 5.02 declared or missing/ambiguous items"
(`:3637`). Item 2.02 deliberately does not own the blank-items bucket:
"the item-502 predicate already owns that ambiguous-items catch-all bucket"
(`:3822-3824`).

**F2 — Lookback is 2 years, chained to the ownership knob.**
`DEFAULT_ITEM_502_LOOKBACK_YEARS = 2` with the comment "Item 5.02 8-K agent
window matches Ticket 20 / agent-source lock (W−2y)" (`:205-208`).
Precedence: explicit `item_502_lookback_years` → `WAREHOUSE_ITEM_502_LOOKBACK_YEARS`
→ ownership lookback → 2 (`:3493-3512`). A filing tagged both 5.02 and 2.02
is kept if inside *either* window (`:3715-3733`).

**F3 — Two ingestion paths write the same table with different idempotency
mechanisms.**
- *Branch A (configured-forms parse)*: `_run_parse_pipeline` dispatches
  `form_family == "item_502"` to `_parse_item_502_accession`
  (`:5378-5388`), which reads the primary attachment's raw object from bronze
  (`:5432-5433`, `_read_primary_artifact_bytes` `:5471-5479`) and merges
  events (`:5442-5457`). Its comment: "Item 5.02 is integrated into Branch A
  configured-forms loads so the ownership + employment load share one
  artifact pass (2y agent window)" (`:5378-5379`). Callers are the
  bronze-then-silver runner under `daily_incremental`, `bootstrap_full`,
  `bootstrap_batch` (`:1234, :1331, :1377, :1809`) and `targeted_resync`
  (`:1449`, parser selection `:1455-1466`). The only re-parse skip on this path is the silver-once gate,
  which fires for `form_family == "ownership"` only (`:3134-3146`,
  `silver_once.py:4,14`) — an Item 5.02 accession inside the window is
  re-parsed every run and idempotency rests entirely on the dbt collapse (F9).
- *Branch B (`bootstrap-fundamentals --mode per-filing`)*: Step Functions
  state `FetchPerFilingFundamentals` (`deploy-aws-application.sh:3776-3787`)
  runs `run_bootstrap_fundamentals_per_filing` (`bootstrap_fundamentals.py:170-177`),
  which scans `sec_company_filing` for `BRANCH_B_FILING_FORMS` (8-K, 8-K/A,
  DEF 14A, DEF 14A/A, DEFA14A, PRE 14A) (`fundamentals_ingest.py:46-49, 173-182`),
  applies the same 2y bound (`:185-214`), parses Item 5.02 when items contain
  `5.02` or are blank (`:293-323`), and marks `sec_fundamentals_processed_accession`
  after the rows (`:324-331`; skip read at `:221-228`). The state's own
  comment still says it produces only "sec_earnings_release, sec_executive_record"
  (`deploy-aws-application.sh:3784-3786`) — `sec_employment_event` is written but undocumented there.

Both paths compute `event_index` as `enumerate(result.events, start=1)`
(`warehouse_orchestrator.py:5455`, `fundamentals_ingest.py:319`) over the
parser's sorted tuple, so an overlap collapses to the same key set (F9).

### Area 2 — parser

**F4 — Entry `parse_item_502(accession_number, cik, filing_date, content)`
→ `Item502Result(applicability, reason_code, events)`** (`item_502.py:524-608`).
`applicability ∈ {applicable, unresolved, not_applicable}`; reason codes
`item_5_02_absent` (`:528`), `named_employment_event` (`:605`),
`unclassified_named_event` (`:607`), `no_named_employment_event` (`:608`).
Per-event fields (`EmploymentEvent`, `:71-80`): `accession_number, cik,
event_type, person_name, role, effective_date, previous_role,
compensation_amount`. `event_type ∈ {appointment, departure, role_change,
compensation_change}` (`:393, :437, :497, :533, :539`). Version: `PARSER_VERSION = "5"` (`:68`).

**F5 — `person_name` is a spaCy dependency-parse reconstruction, not NER and
not a regex field.** `_person_name` takes the head PROPN token and joins its
`compound` PROPN children in document order, collapses whitespace, strips a
trailing `.`, and requires at least two `[A-Z][a-z]` components (`:225-244`).
The only normalization is whitespace/trailing-dot; case, middle initials,
suffixes and honorifics are kept as written. For the two regex-only event
types the name is `match.group("name").strip()` from
`[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3}` (`:103, :110, :533, :539`).
Possessive departures use a `poss`/`nmod` child or a 6-token lookbehind regex
ending in `'s` (`:442-460`). In-filing dedupe is case-folded on
`(event_type, person_name.casefold(), effective_date, role.casefold())` (`:592-600`).

**F6 — Role text is free text, not a vocabulary, with one hard-coded
constant.** `_find_role_and_token` returns `_clean_span(...)` of whichever
child token won — `as [Role]`, `to the position/role/office of [Role]`, the
bare `oprd` object-predicate, or `promoted to [Role]` (`:251-307`);
`_clean_span` is the token's left-edge span stripped of ` ,.` (`:314-316`).
The literal `"Director"` is returned for "to the Board" (`:286`), for any
sentence matching `_BOARD_DIRECTOR` (`board of directors|as (a )?directors?|to
the board|on the board`, `:116-119`, `:305-306`, `:361-362`), and as the
appointment fallback `role or "Director"` (`:394`); departures get
`"Director"` only via the same regex, else `None` (`:433-435`). This is the
code origin of research 01 F2's distribution ("Director" 2,661 / null 2,637 /
"a member" 246 / "directors" 84): "a member" and "directors" are raw
`_clean_span` output. `test_item_502_promoted_to_role_without_as_or_position_of`
pins that "Executive Vice President, Chief Revenue Officer" is stored as
`"Executive Vice President"` (`tests/unit/test_item_502_parser.py:352`) —
the span stops at the comma.

**F7 — `effective_date` is "nearest `Month D, YYYY` DATE entity to the verb",
with three fallbacks.** `_find_date` parses every DATE entity in the sentence,
picks the one closest to the verb token, then `effective immediately` →
`filing_date`, then any calendar date anywhere in the sentence, then, on the
second call only, `filing_date` (`:319-342`, `:365-370`, `:404-408`,
`:486-491`). Consequence pinned by test: "On July 26, 2024, Lucy To ... was
appointed ... with a start date of August 12, 2024" yields
`effective_date == 2024-07-26` — the board-action date, not the start date
(`tests/unit/test_item_502_parser.py:314-326`). `role_change`/`compensation_change`
take the regex's trailing date (`:104-105, :111`).

**F8 — Same person can appear as multiple rows per filing; the docstring's
"never fabricate" rule and its deliberate non-fixes.** Dedupe is by the
4-tuple in F5, so one filing yields one row per distinct
(event_type, name, date, role): e.g. an appointment and a same-person
`role_change` are both kept, and every appointment verb/conjunct is a row
(`:382-396`; the two-name Brown-Forman fixture asserts two events,
`tests/unit/test_item_502_parser.py:125-137`). Output is sorted by
`(effective_date, person_name, event_type)` (`:601-604`). v5's own rule,
verbatim: "Both are purely additive under-extraction fixes: they can only
turn a real, already-disclosed person+role+date into a resolved event, never
fabricate one, so they carry no false-positive risk. Deliberately NOT fixed
here: backward-references to prior filings ("as previously disclosed... had
appointed"), bio-background prose, appositive names, and nominalized
"approved the appointment of X" — those are suppression-shaped fixes (would
turn `unresolved` into `not_applicable`, which nothing downstream re-checks)
and can silently drop a real event if the same filing also discloses one
under a different construction (confirmed on a real accession); left as
pending backlog rather than rushed." (`:44-54`). Known residual rate in the
same docstring: "~10.6%" unresolved after v4 (`:35-36`); v4 cites "9.5%
unresolved rate across a 400-sample scan" (`:32`). Structural rejections:
conditional clauses (`:206-222`), modifier participles such as "newly
appointed" (`:506-512`), and the statutory title line (`:515-521`).
`apply_employment_events`/`EmploymentVersion` (`:611-649`) have **no
non-test consumer** anywhere in `edgar_warehouse/` — dead code; the live
versioning is in `pipeline.py` (F13).

**Tests (fixture count).** `tests/unit/test_item_502_parser.py`: 18 test
functions, 19 inline content fixtures, 0 stored HTML files; 7 are
real-accession-backed (CIKs 315213, 14693 ×2, 14707 ×2, 1833214, 88000).
Shapes covered: passive/active appointment, `as`/`to the board`/`oprd`/
`promoted to` roles, vacancy election, active-voice termination, possessive
resignation/retirement, "stepped down", "joined as", newly-appointed
modifier, 5.07 vote-tally isolation, bulleted roster. Not covered: any
assertion of `applicability == "unresolved"`/`unclassified_named_event`
(grep finds the string only in docstrings, `:78, :368`), per-filing row
*counts* for one person with several events (the roster test asserts
membership only, `:397-401`), and the four "deliberately NOT fixed"
constructions. `tests/unit/test_item_502_branch_a_parse.py` (5 tests) pins
family routing and `_run_parse_pipeline` dispatch; `tests/mdm/test_pipeline_relationships.py`
has 4 employment-event tests (F13).

### Area 3 — silver

**F9 — Landing table, key, collapse.** `sec_employment_event(accession_number
TEXT NN, event_index BIGINT NN, cik BIGINT NN, event_type TEXT NN,
person_name TEXT NN, exec_role TEXT, previous_role TEXT, compensation_amount
DOUBLE, effective_date DATE NN, parser_version TEXT NN, ingested_at
TIMESTAMP_TZ, parse_sequence)` (`11_silver_landing_schema.sql:359-374`;
snapshot `silver_schema.py:234-246`, NOT NULL set `:579-587`). Writer:
`merge_employment_events` → `_record_landing_passthrough` with
`ingested_at` stamp (`silver_landing_store.py:581-584`, `:379-431`); the
stamp's docstring says MDM "filters sec_executive_record/sec_employment_event
on it as a watermark" (`:479-480`). The dbt collapse keeps the latest
`parse_sequence` per `(accession_number, event_index)` and anti-joins
`SILVER_LANDING_RETIREMENT` (`models/silver/sec_employment_event.sql:21-25`).
Because `event_index` is positional over a parser-sorted list (F3), a parser
version that changes event count or order re-points existing keys, and no
code path writes a retirement for this table (the only
`silver_landing_retirement` writer is `acquisition/reference_catalog_silver_acceptance.py:328`,
unrelated) — a row an older parser emitted stays live until a newer parse
overwrites its index.

**F10 — No `mdm_entity_id` column and no back-propagation.** The column
exists only on `sec_adv_filing`, `sec_adv_private_fund`, `sec_company` and
the three ownership tables (`silver_schema.py:61, 108, 145, 403, 420, 434`);
`mdm_entity_backfill.py`'s `_TABLE_SPECS` lists those six and not
`sec_employment_event` (`:106-151`). Source-layer passthrough:
`_build_sec_employment_event` (`source_dimensional_export.py:348-367`) →
`EDGARTOOLS_SOURCE.SEC_EMPLOYMENT_EVENT`, whose comment reads "Employment /
Item 5.02 events for EMPLOYED_BY. Passthrough from silver sec_employment_event."
(`01_source_stage.sql:446-458`). **No gold model reads it**:
`executive_records.sql` refs `sec_executive_record` only (`:36`); the only dbt
references are `sources.yml:59, 129` and the silver model.

### Area 4 — legacy MDM

**F11 — No resolver consumes it; the Person is created inside relationship
derivation.** `PersonResolver` is "Form 3/4/5 reporting-owner resolution"
(`resolvers/person.py:1-7`) and never reads `sec_employment_event`. The
only consumer is `_derive_employed_by`, dispatched for `EMPLOYED_BY`
(`pipeline.py:1726-1729`), whose event branch runs after the DEF 14A branch
in one method (`:3903-4051`). Query: all rows, `ingested_at > watermark`
(`EMPLOYED_BY:event` checkpoint, `:3906-3918`; two-key checkpoint rationale
`database.py:684-689`), ordered by `effective_date, accession_number, event_index`.

**F12 — How a name-only row becomes a Person: global exact-name match, then
a per-issuer UUID5 stub; the documented "Form 4 anchor" is unreachable.**
The branch calls `self._person_entity_id(None, person_name)` (`:3952`), then
`_ensure_proxy_person(person_name, cik, accession_number)` for any of the
four event types (`:3953-3959`). `_person_entity_id` with `owner_cik=None`
skips the CIK branch and runs
`select(MdmPerson.entity_id).where(MdmPerson.canonical_name == owner_name)`
(`:3247-3260`) — an exact, case-sensitive string equality across **all**
persons, with no issuer context. `_ensure_proxy_person` repeats that lookup
(`:3546`), then mints `uuid5(NAMESPACE_DNS, f"{company_cik}:{normalized}")`
where `normalized = NFKD(exec_name.strip().lower())` (`:3551-3552`), and
writes `MdmEntity(entity_type="person", resolution_method="uuid5_proxy_stub",
confidence=0.5)`, `MdmPerson(canonical_name=exec_name.strip(),
name_variants=[exec_name.strip()])`, an `MdmSourceRef(source_system="proxy_filing",
source_id=accession_number, source_priority=50, confidence=0.5)` and a
change-log row (`:3564-3595`). Three code-vs-docstring facts:
- Both docstrings promise a CIK anchor — "1. Exact Form 4 anchor via
  _person_entity_id" (`:3753`) and "1. Exact CIK match via _person_entity_id
  (Form 4 anchor)" (`:3526`) — but both call sites pass `None` for the CIK
  (`:3952, :3546`). No 8-K row ever carries a CIK for the person.
- The name-equality step compares the parser's raw `"Kathleen M. Gutmann"`
  against `canonical_name`, which for resolver-created persons is the staged
  normalized form (`resolvers/person.py:76, 116, 200-203`;
  `normalize_name` lowercases and strips punctuation, `rules.py:152-161`).
  Exact equality between those two forms cannot hold, so the Form 4 path
  is effectively dead for 8-K names and the stub path fires.
- The docstring says "UUID5 deduplication is intentionally per-company
  (AD-06). An exec named 'John Smith' at AAPL (cik=320193) and at MSFT
  (cik=789019) will receive two different entity_ids" (`:3530-3532`). But
  step 2 (`:3546`) matches `canonical_name` globally, and a stub's
  `canonical_name` is the raw stripped name (`:3573`), so the second issuer's
  "John Smith" resolves to the first issuer's stub before step 3 runs.
  **Cross-issuer name-only binding is live in legacy** — the exact thing
  research 01 F3 says a name must never do.
- Stub provenance is mislabeled for this source: the entity's source ref and
  change-log say `proxy_filing` (`:3580, :3591`) regardless of caller, while
  the edge says `source_system="item_502_filing"` (`:4035`).

**F13 — EMPLOYED_BY derivation, properties, closing.** Per event, after
resolving the company by CIK (`:3932-3947`): `departure` requires exactly one
open version for the pair and closes it at `effective_date` via
`close_relationship_version` (`:3964-3993`); `appointment`/`role_change`/
`compensation_change` close any single open version then insert a new one
with `properties={role, title, previous_role, compensation_amount,
source_accession, event_type}`, `effective_from=effective_date`,
`source_system="item_502_filing"`, `date_provenance="reported"`
(`:3994-4038`). `role`/`title` fall back to the prior open version's
(`:4023-4028`). Guards: an event whose date is `<=` the open version's
`effective_from` is skipped with `event_predates_open_version`
(`:3969-3990, :4002-4014`), because proxy baselines carry "effective_from =
Jan 1 of the DEF 14A fiscal year -- a coarse placeholder, not a true start
date" (`:3971-3974`) and `ck_rel_instance_valid_interval` needs a strictly
positive interval (`:3976-3979`). More than one open version → skipped
(`:3999-4001`). Registered closing pattern:
`"EMPLOYED_BY": "property_differs_from_prior"` (`:192`; ADR 0008 line 10),
though the docstring notes "The event/Item 5.02 branch below is untouched --
it already has its own bespoke closing mechanism" (`:3775-3778`). Tests:
appointment opens a version (`test_pipeline_relationships.py:923-949`),
event-before-baseline skipped (`:951-1007`), same-day events skipped
(`:1009-1060`), stub change-log for export (`:891-915`). Coverage check for
`EMPLOYED_BY` reads `sec_executive_record` only, despite its
`evidence_query_version="edge09-v2-proxy-item502"` (`coverage.py:414-419`).

### Area 5 — downstream

**F14 — Graph: allowed, viewed, never populated; two serving readers with a
vocabulary mismatch.** `EMPLOYED_BY` is in `ALLOWED_RELATIONSHIP_TYPES`
(`snowflake_graph.py:25`) with a `GRAPH_EDGE_EMPLOYED_BY` view (`:68, :1599-1602`)
but not in `POPULATED_RELATIONSHIP_TYPES = ("COMPANY_HOLDS", "HOLDS",
"ISSUED_BY", "IS_INSIDER")` (`:52`); the comment: "Phase 6 (fix-pipelines)
investigated 5 of these 7 (... EDGE-09 EMPLOYED_BY ...) and confirmed NONE
reached graph-populated status" (`:42-45`). Readers: `insider_watch.screen`
joins `MDM_GRAPH_EDGES` where `relationship_type = 'EMPLOYED_BY'` for
`owner_role` (`dashboard_workflows.py:236-246`); the issuer subject bundle's
employment section keys persons by `person_entity_id` else
`name:<lower>` (`subject_bundle_read.py:393-400`) and expects
`source_system ∈ {"proxy_def14a", "item_5_02"}` (`:40-42`) — neither equals
what the pipeline writes (`proxy_filing`, `item_502_filing`), and the
"mark non-standard" comment at `:227` is not implemented (`:228` leaves a
non-empty value untouched). No `mdm/api/` router names `EMPLOYED_BY`
(grep). Clean MDM's projection registry already types it
`"EMPLOYED_BY": ({"person"}, {"company"}, None, None)` (`mdm/clean/relationships.py:15`).

### Area 6 — Clean MDM's stated target

**F15 — Row 26 of the inventory, verbatim** (`pipeline-inventory.md`, inspected at commit
`b1babd8`): `| Proxy/officer — mdm/pipeline.py:3743, :3520 | sec_executive_record,
sec_employment_event | Person lookup/stub creation inside derivation; dated
EMPLOYED_BY, compensation/role properties | Identity first, then reported
employment; no direct stub master writes; provenance includes event and
filing dates |`. Row 23 (Ownership Person) targets "Person assertions with
source-specific capacities". `domain-model.md`: Person is "A natural person
... Never merge with a Company, employer, sole-proprietor business, or
similarly named person through a role." (line 12); `EMPLOYED_BY` "Person to
Company | Source-reported office/role and valid dates; holdings do not imply
employment" (line 68); "Every adapter submits evidence to the Merge Stage;
no bulk writer, relationship stub helper, steward, or repair command may
retain a second master-state mutation path." (lines 93-95); "Legacy IDs
become an explicitly verified, versioned crosswalk to new identities and
profiles; ambiguous mappings remain unresolved." (lines 87-88).

## What this settles for tickets 02/03/05/06

- **02 (what binds):** the 8-K source carries no person identifier at all —
  `person_name` is free text from a dependency parse (F5); `exec_role` is
  free text plus one constant (F6). The only deterministic context is
  `(cik, person_name)`; legacy's stub key is exactly that,
  `uuid5(cik:lower(name))` (F12). Legacy also binds by exact global name
  across issuers (F12), which the Person contract must forbid.
- **03 (relationships/projection):** legacy `EMPLOYED_BY` from this source
  has `effective_from` = parser `effective_date` (board-action date, not
  start date, F7), `properties.role` = raw span, `event_type` carried as a
  property, `source_system="item_502_filing"` (F13). One filing can emit
  several rows per person (F8). The edge has never been graph-populated
  (F14), so nothing downstream depends on its current shape.
- **05 (privacy/retention):** rows are never retired; positional
  `event_index` means a corrected parse overwrites, never deletes (F9).
  No `mdm_entity_id` on the silver row (F10). Stub persons have
  `confidence=0.5`, `source_priority=50` and mislabeled `proxy_filing`
  provenance (F12).
- **06 (migration/crosswalk):** every 8-K-only legacy Person is a
  `uuid5_proxy_stub` (F12) whose `canonical_name` convention (raw Title Case)
  differs from resolver persons (normalized lowercase); the crosswalk cannot
  assume one convention. Clean MDM's line 93-95 prohibition names
  `_ensure_proxy_person`'s pattern directly (F15).
- **Tests/gates (any ticket):** no test pins the `unresolved` outcome or
  per-person row counts (F8); the serving source-system vocabulary is
  already inconsistent with the pipeline (F14).

## Could not be determined from code

- Whether Form 3/4/5 `owner_name` is surname-first ("GUTMANN KATHLEEN M");
  `parsers/ownership.py:30` passes edgartools' `owner.name` through
  unchanged. If it is, the 8-K/Form 4 name match fails on token order as
  well as case, but that is a data fact.
- Whether any resolver-created `MdmPerson.canonical_name` is ever the raw
  name: `_upsert_golden` falls back to `raw_name` only when survivorship
  has no winner (`resolvers/person.py:186`); how often that happens is a
  data question.
- Actual unresolved/`not_applicable` rates for the deployed image (the
  docstring's 9.5%/10.6% figures are historical scope checks).
- Whether the generic graph API traversal (`mdm/api/routers/graph.py`)
  returns `EMPLOYED_BY` edges: it names no relationship type, and with the
  type never populated (F14) there is no live evidence either way.
- How many 8-K persons collided with a same-name stub from another issuer
  via `pipeline.py:3546` in prod — the mechanism is certain, the count is not.
