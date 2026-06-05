# Phase 10: Live ADV Backfill Validation — Research

**Researched:** 2026-06-04
**Domain:** ADV bronze-to-silver backfill validation, MDM adviser/fund preflight, operator runbook documentation
**Confidence:** HIGH (codebase + live S3 state verified directly)

---

## CRITICAL FINDING: PRECONDITIONS UNMET — DECISION REQUIRED

**Phase 10 as written in REQUIREMENTS.md (MDM-ADV-01: nonzero `sec_adv_filing` and
`sec_adv_private_fund` after live backfill) is unexecutable against the current dev S3
environment.**

Root cause: The dev S3 bronze contains **zero ADV filing artifacts**. All 752 CIK directories
in `s3://edgartools-dev-bronze-077127448006/warehouse/bronze/filings/sec/` belong to
large-cap public equity companies (NVDA, AAPL, MSFT, BRK, etc.). Investment advisers are
separate SEC registrant entities with their own CIK numbers and file Form ADV as a distinct
registration class — none of the 100 tracked public companies file Form ADV.

**Live silver confirmation:**
```
sec_adv_filing:           0 rows   (main silver.duckdb + shard-0.duckdb, both checked)
sec_adv_office:           0 rows
sec_adv_disclosure_event: 0 rows
sec_adv_private_fund:     0 rows
sec_company_filing (ADV%): 0 rows  (out of 2,858,889 total filings across all form types)
```

This means `discover_adv_bronze_artifacts()` (the registry path in `parse-adv-bronze`)
has nothing to discover. The explicit `--artifact` path also has nothing to point at —
no ADV XML objects exist in S3.

**The out-of-scope constraint blocks the obvious workaround:** STATE.md explicitly records
"Do not fetch missing ADV artifacts from SEC." REQUIREMENTS.md Out of Scope: "Fetching
missing ADV artifacts from SEC." Bootstrapping an investment adviser CIK via
`edgar-warehouse bootstrap --cik-list <adviser_cik>` is an SEC fetch operation. This
approach directly violates the milestone's locked constraint.

**The planner needs a user decision before writing a live-data plan:**

| Fork | MDM-ADV-01 | MDM-ADV-02 | MDM-ADV-03 | Constraints |
|------|-----------|-----------|-----------|-------------|
| **A — Relax no-fetch to allow one-time adviser bootstrap** | Live counts achievable | Live preflight achievable | Documentable | Requires explicit user approval to override the locked constraint |
| **B — Fixture-based: descope live data, prove preflight flow with populated fixture DuckDB** | Marked as "fixture only" rather than live | Demonstrable via fixture | Documentable now | No constraint change needed |
| **C — Docs-only: deliver MDM-ADV-03, defer MDM-ADV-01 and MDM-ADV-02** | Deferred | Deferred | Delivered | No constraint change; unblocks Phase 5 resume docs immediately |

**Surface this as the #1 Open Question before planning.**

---

<user_constraints>
## User Constraints (from STATE.md / CONTEXT.md decisions)

### Locked Decisions
- Use the isolated git worktree at `/Users/aneenaananth/gsd-workspaces/neo4j-pipe/edgartools-platform`.
- Keep the backfill AWS/local only: existing S3/local bronze artifacts in, silver ADV tables out.
- **Do not fetch missing ADV artifacts from SEC during this milestone.**
- Prefer registry-backed reads (`sec_filing_attachment` + `sec_raw_object`) when available; include an explicit bounded fallback for existing bronze object paths.
- Reuse `edgar_warehouse.parsers.adv` and `SilverDatabase.merge_adv_*` — do not add a new ADV parser.
- Keep the workstream isolated from loader-fix artifacts, generated deployment JSON, gold/dbt, Snowflake graph sync, and generic Step Functions work.
- SEC alternate URL load validation stays in backlog Phase 999.1.
- Phase 5 D-10: "Treat already-captured bronze primary XML as the prerequisite. If XML artifacts are absent, report the gap clearly — do not silently re-fetch SEC data."
- Phase 5 D-14: "The test CIK must have both Forms 3/4/5 bronze AND ADV filing bronze already in S3."
- Phase 5 D-16: MDM target for live tests is local Postgres via Colima.

### Claude's Discretion
- How to structure the operator runbook update for MDM-ADV-03.
- Whether to validate MDM-ADV-02 with a live run or fixture DuckDB, subject to user fork decision above.

### Deferred (OUT OF SCOPE)
- Fetching missing ADV artifacts from SEC.
- Rewriting ADV parser semantics.
- Gold table enrichment or dbt model changes.
- Snowflake graph analytics migration work.
- Non-AWS deployment paths, registries, storage targets, or secret-management paths.
- ADV-specific ECS batch automation (future requirement).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MDM-ADV-01 | After ADV backfill, `sec_adv_filing` and `sec_adv_private_fund` report nonzero rows for at least one selected live S3 ADV sample when source data contains private funds | **BLOCKED** — no ADV bronze in dev S3. Requires fork decision. |
| MDM-ADV-02 | `mdm run --entity-type adviser` and `mdm run --entity-type fund` preflights can succeed against a silver source populated by `parse-adv-bronze` | **BLOCKED on live**; demonstrable with fixture DuckDB via fork B. |
| MDM-ADV-03 | Docs identify the exact resume path for the blocked Phase 5 live checkpoint, including silver counts needed before running MDM adviser/fund loaders | **Deliverable now** — all mechanics fully researched below. |
</phase_requirements>

---

## Summary

Phase 10 was designed to validate the `parse-adv-bronze` command (built in Phase 9)
against actual dev S3 bronze data, proving that ADV silver rows populate correctly and
that the MDM adviser/fund preflight gates (`_require_silver_reader()`) transition from
failing to passing. The research reveals this cannot proceed in the originally intended
form: the dev S3 tracked universe contains only large-cap public equities with no ADV
filings.

The `parse-adv-bronze` command itself is fully functional (Phase 9 complete, 8 tests
passing). The ADV discovery helpers, silver merge methods, idempotency skip logic, and
MDM preflight mechanics are all verified and correct. What is missing is source data:
investment adviser CIK directories are not present in S3 bronze because the bootstrap
pipeline only captured the 100 public company CIKs in `sec_tracked_universe`.

MDM-ADV-03 (docs) is fully deliverable: the mechanics are understood, `docs/aws-mdm-source-to-mdm.md`
already acknowledges "Zero sec_adv_filing = ADV data was not loaded" in its diagnostics
table, and a new "Parse ADV Bronze" step can be written now. The resume path and required
count thresholds are all researched below.

**Primary recommendation:** Deliver MDM-ADV-03 (docs) unconditionally. Escalate the
fork decision for MDM-ADV-01 and MDM-ADV-02 to the user before writing the live
validation plan tasks. Do not allow the plan to assume "run `parse-adv-bronze` and check
counts" — the command will find nothing without prior adviser bootstrap.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ADV bronze artifact selection | API / Backend (`adv_bronze_discovery.py`) | Database (silver DuckDB registry) | Discovery queries `sec_company_filing` + `sec_filing_attachment` + `sec_raw_object` to locate existing S3 objects |
| ADV XML parsing | API / Backend (`parsers/adv.py`) | — | Pure parser — no I/O, no DB |
| Silver ADV table writes | Database / Storage (`silver_store.py`) | — | `merge_adv_*` upserts own all 4 ADV tables |
| MDM adviser/fund preflight | API / Backend (`mdm/cli.py`) | Database (silver DuckDB) | `_require_silver_reader()` validates table counts before MDM session open |
| Operator runbook docs | — | — | `docs/aws-mdm-source-to-mdm.md` is the single operator reference |

---

## Standard Stack

No new libraries are required. All components are already installed.

### Core (already present)

| Component | Version/Location | Purpose |
|-----------|-----------------|---------|
| `edgar-warehouse` CLI | `edgar_warehouse/cli.py` | Exposes `parse-adv-bronze` subcommand |
| `_run_parse_adv_bronze` | `warehouse_orchestrator.py:1821` | Orchestrator branch for ADV backfill |
| `discover_adv_bronze_artifacts` | `application/adv_bronze_discovery.py` | Registry + explicit-path discovery |
| `read_adv_bronze_artifacts` | `application/adv_bronze_discovery.py` | S3 read with unreadable-artifact tolerance |
| `parse_adv` | `parsers/adv.py` | ADV XML → 4-table row dict |
| `merge_adv_*` | `silver_store.py` | Upsert into 4 ADV silver tables |
| `_require_silver_reader` | `mdm/cli.py:~line 340` | MDM preflight gate |
| DuckDB | already in `uv.lock` | Silver DuckDB storage |

**Installation:** None required. `uv sync --extra s3` covers all dependencies.

---

## Package Legitimacy Audit

Not applicable — Phase 10 installs no new packages.

---

## Architecture Patterns

### Data Flow (when ADV bronze exists)

```
S3 bronze ADV XML
        |
        v
adv_bronze_discovery.discover_adv_bronze_artifacts(db)
  - queries sec_company_filing WHERE form IN ('ADV', 'ADV/A', ...)
  - joins sec_filing_attachment + sec_raw_object to get storage_path
  - falls back to explicit --artifact ACCESSION,FORM,S3_PATH[,CIK]
        |
        v
adv_bronze_discovery.read_adv_bronze_artifacts(candidates)
  - reads bytes from storage_path via object_storage.read_bytes
  - records unreadable paths without aborting batch
        |
        v
parse_adv(accession, content, form, cik)
  --> { sec_adv_filing: [...], sec_adv_office: [...],
        sec_adv_disclosure_event: [...], sec_adv_private_fund: [...] }
        |
        v
silver_store.merge_adv_filings / merge_adv_offices /
merge_adv_disclosure_events / merge_adv_private_funds
  - ON CONFLICT ... DO UPDATE upserts per primary key
        |
        v
silver DuckDB (all 4 ADV tables populated)
        |
        v
mdm run --entity-type adviser   [requires sec_adv_filing nonempty]
mdm run --entity-type fund      [requires sec_adv_private_fund nonempty]
```

### MDM Preflight Gate (from `mdm/cli.py`)

```python
# _REQUIRED_TABLES_RUN at line 340-361 (VERIFIED: codebase)
"adviser": { "sec_adv_filing": True },      # must be nonempty
"fund":    { "sec_adv_private_fund": True }, # must be nonempty
```

`_require_silver_reader()` runs BEFORE any MDM session is opened. If the table is empty,
the command exits with a clear diagnostic — it does not silently succeed.

`mdm run --entity-type all` does NOT require ADV tables to be nonempty (ADV tables are
excluded from the "all" non-empty requirement). Only `--entity-type adviser` and
`--entity-type fund` gate on ADV.

### Idempotency

Two-layer idempotency:
1. **Skip layer (before S3 read):** `_run_parse_adv_bronze` queries `sec_adv_filing` for already-parsed accession numbers and excludes them from the candidate list before calling `read_adv_bronze_artifacts`. Storage reads are not performed for already-parsed accessions.
2. **Upsert layer (during merge):** `merge_adv_*` uses `ON CONFLICT ... DO UPDATE`. Even if the skip layer is bypassed (e.g., via a repair flag), the merge is idempotent.

### Required Environment Variables

`parse-adv-bronze` is NOT in `SERVING_EXPORT_COMMANDS`, so it does NOT require
`SERVING_EXPORT_ROOT` or `MDM_DATABASE_URL`. [VERIFIED: codebase — `warehouse_settings.py`]

Minimum required vars:
```bash
export EDGAR_IDENTITY="EdgarTools Platform email@example.com"  # must contain @email
export WAREHOUSE_RUNTIME_MODE="bronze_capture"
export WAREHOUSE_BRONZE_ROOT="s3://edgartools-dev-bronze-077127448006/warehouse/bronze"
export WAREHOUSE_STORAGE_ROOT="s3://edgartools-dev-warehouse-077127448006/warehouse"
# AWS credentials must be active (AWS_DEFAULT_REGION=us-east-1)
```

`WAREHOUSE_SILVER_ROOT` is auto-derived from `WAREHOUSE_STORAGE_ROOT` as
`{WAREHOUSE_STORAGE_ROOT}/silver/sec/silver.duckdb` unless overridden.

### CLI Invocation Patterns

```bash
# Registry-backed: parse all ADV accessions found in silver registry
edgar-warehouse parse-adv-bronze

# With limit: parse at most 10 not-yet-parsed ADV accessions
edgar-warehouse parse-adv-bronze --limit 10

# Targeted: parse specific accessions only
edgar-warehouse parse-adv-bronze --accession-list 0001234567-23-000001,0001234567-23-000002

# Explicit artifact path (when registry rows are absent):
edgar-warehouse parse-adv-bronze \
  --artifact "0001234567-23-000001,ADV,s3://edgartools-dev-bronze-077127448006/warehouse/bronze/filings/sec/cik=1234567/accession=0001234567-23-000001/primary_doc.xml,1234567"
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ADV XML to silver rows | Custom parser | `parsers/adv.parse_adv()` | Already handles all 4 ADV tables; Phase 9 confirmed it works |
| Silver upserts | Manual INSERT | `silver_store.merge_adv_*()` | Primary-key conflict handling is subtle; upserts handle repair runs |
| Bronze artifact discovery | Custom S3 scanner | `adv_bronze_discovery.discover_adv_bronze_artifacts()` | Registry-backed + explicit fallback already implemented; reinventing breaks idempotency |
| MDM preflight checks | Re-implementing table count logic | `mdm/cli._require_silver_reader()` | Single source of truth for MDM table requirements per entity type |

---

## Runtime State Inventory

Not applicable — this phase does not rename or refactor any strings or identifiers.

---

## Common Pitfalls

### Pitfall 1: Assuming `parse-adv-bronze` Will Find ADV Bronze Artifacts
**What goes wrong:** Running `edgar-warehouse parse-adv-bronze` against dev S3 without first bootstrapping an investment adviser CIK produces zero processed accessions and zero silver rows. The command exits successfully (it found nothing to parse, which is correct behavior), so there is no error signal.
**Why it happens:** The dev tracked universe is 100 large-cap public equities. None file Form ADV. The ADV discovery query `SELECT ... FROM sec_company_filing WHERE form IN ('ADV', 'ADV/A', ...)` returns 0 rows.
**How to avoid:** Verify `sec_company_filing` has ADV-form rows BEFORE running `parse-adv-bronze`. Query: `SELECT COUNT(*) FROM sec_company_filing WHERE form LIKE 'ADV%'`.
**Warning signs:** `parse-adv-bronze` exits immediately with 0 discovered, 0 parsed metrics.

### Pitfall 2: Conflating `mdm run --entity-type all` With Adviser/Fund Readiness
**What goes wrong:** `mdm run --entity-type all` succeeds even when ADV tables are empty, because `_REQUIRED_TABLES_RUN("all")` excludes ADV tables from the non-empty requirement. This masks the absence of adviser/fund data.
**Why it happens:** "all" allows partial silver coverage — the system can load companies, persons, and securities without ADV data present.
**How to avoid:** Test adviser/fund preflight explicitly with `--entity-type adviser` and `--entity-type fund`, not `--entity-type all`.
**Warning signs:** `mdm run --entity-type all` succeeds, but `mdm run --entity-type adviser` immediately exits with a preflight error referencing `sec_adv_filing`.

### Pitfall 3: Investment Adviser CIKs Are Not in the Tracked Universe
**What goes wrong:** Searching the tracked universe for a "company that files ADV" returns nothing, because the tracked universe is public equities and investment advisers are a separate SEC registrant class.
**Why it happens:** Large-cap equities (NVDA, AAPL, etc.) are registered as public companies. Registered investment advisers have entirely separate CIK registrations under Form ADV/IARD. Even companies like BlackRock that have both a public company entity AND an investment adviser entity have separate CIK numbers for each.
**How to avoid:** Search the SEC EDGAR company search directly for investment advisers (SIC code 6282 = Investment Advice, or search by form type ADV). Do not look for ADV-filing CIKs within `sec_tracked_universe`.
**Warning signs:** `sec_company.entity_type` for tracked companies will be 'operating' or similar, not 'investment-adviser'.

### Pitfall 4: Fixture-Based Validation Does Not Prove Command Against S3
**What goes wrong:** Using a pre-populated DuckDB fixture to test the MDM preflight transition proves the preflight logic but does not prove `parse-adv-bronze` correctly reads ADV artifacts from S3 and populates silver.
**Why it happens:** Fixture tests bypass the S3 read path entirely.
**How to avoid:** Clearly document in the plan which parts are fixture-validated vs. live S3 validated. MDM-ADV-02 can be fixture-validated. MDM-ADV-01 requires live S3 data (fork A) or should be explicitly deferred.

### Pitfall 5: `docs/aws-mdm-source-to-mdm.md` Has No `parse-adv-bronze` Step
**What goes wrong:** The operator runs the Phase 5 live checkpoint in order, hits `mdm run --entity-type adviser` and gets a preflight failure. The diagnostic message says "Zero sec_adv_filing = ADV data was not loaded" but the runbook has no `parse-adv-bronze` step to guide the fix.
**Why it happens:** The runbook was written before `parse-adv-bronze` existed (Phase 9 just completed).
**How to avoid:** Add a "Step 1b: Parse ADV Bronze" section to `docs/aws-mdm-source-to-mdm.md` as part of MDM-ADV-03.

---

## Code Examples

### Querying Pre-Run Readiness (Before Running `parse-adv-bronze`)

```python
# Source: codebase — adv_bronze_discovery.py ADV form allowlist [VERIFIED: codebase]
import duckdb

con = duckdb.connect("path/to/silver.duckdb")

# Check if there are ADV forms in the filing registry
adv_count = con.execute("""
    SELECT COUNT(*) FROM sec_company_filing
    WHERE form IN ('ADV', 'ADV/A', 'ADV-E', 'ADV-E/A',
                   'ADV-H', 'ADV-H/A', 'ADV-NR', 'ADV-W', 'ADV-W/A')
""").fetchone()[0]
print(f"ADV forms in registry: {adv_count}")  # Must be > 0 for parse-adv-bronze to work

# Check current ADV silver table states
for tbl in ['sec_adv_filing', 'sec_adv_office',
            'sec_adv_disclosure_event', 'sec_adv_private_fund']:
    n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    print(f"{tbl}: {n} rows")
```

### MDM Adviser Preflight Verification

```bash
# Source: mdm/cli.py _REQUIRED_TABLES_RUN [VERIFIED: codebase]
# This will FAIL if sec_adv_filing is empty (by design — it is the precondition check)
edgar-warehouse mdm run --entity-type adviser --dry-run

# If it passes, sec_adv_filing is nonempty and MDM adviser load is ready
# If it fails with preflight error, sec_adv_filing still needs population
```

### Adding a Fixture DuckDB for Preflight Testing (Fork B)

```python
# Source: Phase 9 test patterns [VERIFIED: codebase tests/application/test_parse_adv_bronze.py]
import duckdb, tempfile, os

def make_adviser_fixture_db():
    """Create a minimal DuckDB with one sec_adv_filing row to prove preflight passes."""
    with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
        db_path = f.name
    con = duckdb.connect(db_path)
    # Create the minimal table structure expected by _require_silver_reader
    con.execute("""
        CREATE TABLE sec_adv_filing (
            accession_number VARCHAR PRIMARY KEY,
            cik BIGINT,
            form VARCHAR,
            filing_date DATE,
            sync_run_id VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO sec_adv_filing VALUES
        ('0001234567-23-000001', 1234567, 'ADV', '2023-01-01', 'test-run-1')
    """)
    con.close()
    return db_path
```

### Verifying MDM Preflight Transition (Before → After)

```bash
# Before: expect preflight failure
WAREHOUSE_SILVER_ROOT=/path/to/empty-adv.duckdb \
  edgar-warehouse mdm run --entity-type adviser
# Expected: exits nonzero, prints "sec_adv_filing must be nonempty"

# After parse-adv-bronze populates sec_adv_filing:
WAREHOUSE_SILVER_ROOT=/path/to/populated-adv.duckdb \
  edgar-warehouse mdm run --entity-type adviser
# Expected: proceeds past preflight, begins entity load
```

### Runbook Step to Add to `docs/aws-mdm-source-to-mdm.md`

```markdown
## Step 1b: Parse ADV Bronze (Required for Adviser and Fund Entity Types)

Before running `mdm run --entity-type adviser` or `mdm run --entity-type fund`,
investment adviser CIKs must have their ADV filing XML parsed into silver.

**Prerequisites:** At least one investment adviser CIK must have been bootstrapped
via `edgar-warehouse bootstrap` so that ADV bronze XML artifacts exist in S3.

```bash
# Parse all ADV bronze artifacts found in the silver filing registry
edgar-warehouse parse-adv-bronze

# Or with a limit for initial testing:
edgar-warehouse parse-adv-bronze --limit 10

# Verify results:
# sec_adv_filing and sec_adv_private_fund must be nonzero before proceeding
```

**Required silver counts before MDM adviser/fund load:**
- `sec_adv_filing`: > 0 rows (required for `mdm run --entity-type adviser`)
- `sec_adv_private_fund`: > 0 rows (required for `mdm run --entity-type fund`)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ADV silver populated only via the full capture pipeline | `parse-adv-bronze` operator command: bronze-only, no SEC fetch | Phase 9 (2026-06-04) | Enables ADV silver backfill from existing S3 artifacts without re-running the full pipeline |
| MDM adviser/fund load had no preflight | `_require_silver_reader()` enforces nonempty ADV tables before MDM adviser/fund mutation | Phase 5 Plans 05-03/05-04 | Prevents silent empty-load failures |

**Deprecated/outdated:**
- Phase 5 D-10 assumption that a test CIK could have "both Forms 3/4/5 bronze AND ADV filing bronze already in S3": falsified — the tracked universe contains no ADV filers. The Phase 5 live checkpoint (Plan 05-05) was blocked for this reason.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Investment advisers filing Form ADV in EDGAR are accessible via the standard `edgar-warehouse bootstrap --cik-list` path (same submissions.json ingestion route) | Open Questions | If ADV-family filings require IARD-specific ingestion (not EDGAR submissions.json), the "relax no-fetch" fork A would require a different ingestion approach, not just a CIK bootstrap |

**All other claims in this research were verified against the codebase and live S3 environment.**

---

## Open Questions

1. **Can an investment adviser CIK be bootstrapped via the standard EDGAR submissions.json path? [CRITICAL FOR FORK A]**
   - What we know: `edgar-warehouse bootstrap` fetches `submissions.json` from `https://data.sec.gov/submissions/CIK{cik}.json`. Investment advisers have EDGAR CIK registrations. SEC EDGAR does list investment advisers.
   - What's unclear: Whether Form ADV filings appear in `submissions.json` "filings" array with form type "ADV" (same as ownership forms), or whether ADV filings are indexed differently / not indexed at all in EDGAR submissions. IARD (Investment Adviser Registration Depository) is a separate SEC system and ADV filings through IARD may not appear in EDGAR submissions.json the same way.
   - Risk: If ADV XML does not appear in `submissions.json` filings, the standard bootstrap won't capture ADV bronze even if an adviser CIK is added to the tracked universe. The explicit `--artifact` path would then require knowing S3 paths ahead of time, which creates a circular dependency.
   - Recommendation: **Before planning Fork A**, verify with one real investment adviser CIK (e.g., look up a known adviser on EDGAR full-text search, get their CIK, check their submissions.json to see if ADV forms appear in the filings array). This is a 5-minute web check against `https://data.sec.gov/submissions/CIK{padded_cik}.json`.
   - [ASSUMED] — not verified in this research session (would require SEC API call or external lookup)

2. **Which fork does the user choose for MDM-ADV-01 and MDM-ADV-02?**
   - What we know: Fork A requires relaxing the no-SEC-fetch constraint; Fork B uses fixture data and marks live validation as deferred; Fork C delivers only MDM-ADV-03 (docs).
   - What's unclear: User preference. All three forks can be planned, but they produce very different task lists.
   - Recommendation: Ask the user directly before writing the plan. The answer determines whether Phase 10 is a 30-minute docs task or a multi-step live data acquisition exercise.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `edgar-warehouse` CLI | parse-adv-bronze execution | ✓ | Phase 9 complete | — |
| AWS CLI + credentials | S3 bronze read | ✓ | Active (confirmed: S3 ls worked during research) | — |
| DuckDB | Silver reads | ✓ | In uv.lock | — |
| `uv` | Python execution | ✓ | Project-standard | — |
| ADV bronze artifacts in S3 | MDM-ADV-01, MDM-ADV-02 live validation | **✗** | 0 ADV objects confirmed | Fork B (fixture) or Fork A (adviser bootstrap, requires constraint relaxation) |
| Local Postgres via Colima | MDM adviser/fund load (live) | Unknown | Not verified | Colima setup in CLAUDE.md |

**Missing dependencies with no fallback:**
- ADV bronze artifacts in S3 — this blocks MDM-ADV-01 and MDM-ADV-02 (live validation). No fallback that satisfies "live S3 ADV sample." Fork A or Fork B is required for these requirements.

**Missing dependencies with fallback:**
- None (other than the ADV bronze gap above).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (already installed via `uv --extra s3 --with pytest`) |
| Config file | none detected at project root |
| Quick run command | `uv run --extra s3 --with pytest tests/application/test_parse_adv_bronze.py -q` |
| Full suite command | `uv run --extra s3 --with pytest tests/application/ tests/mdm/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MDM-ADV-01 | `sec_adv_filing` and `sec_adv_private_fund` nonzero after live backfill | Integration (live S3) | Manual — requires live ADV bronze | Fork-dependent |
| MDM-ADV-02 | MDM adviser/fund preflight succeeds after `parse-adv-bronze` | Unit (fixture DuckDB) or Integration (live) | `uv run --extra s3 --with pytest tests/mdm/test_adv_preflight.py -q` | ❌ Wave 0 — new file needed |
| MDM-ADV-03 | Docs exist in `docs/aws-mdm-source-to-mdm.md` | Manual review | `grep -n "parse-adv-bronze" docs/aws-mdm-source-to-mdm.md` | ❌ Step not added yet |

### Sampling Rate
- Per task commit: `uv run --extra s3 --with pytest tests/application/test_parse_adv_bronze.py -q`
- Per wave merge: `uv run --extra s3 --with pytest tests/application/ tests/mdm/ -q`
- Phase gate: Full suite green before phase close-out

### Wave 0 Gaps
- [ ] `tests/mdm/test_adv_preflight.py` — preflight fail→pass transition for adviser/fund
- [ ] `docs/aws-mdm-source-to-mdm.md` — new "Parse ADV Bronze" step

*(Existing `tests/application/test_parse_adv_bronze.py` covers ADV-04 through ADV-07; no gaps there.)*

---

## Security Domain

No new security surfaces in Phase 10. The `parse-adv-bronze` command reads S3 artifacts
using existing `read_bytes` infrastructure (same as `parse-ownership-bronze`). No new
auth, session management, or cryptography concerns. Input validation for `--artifact`
is already implemented in Phase 9 CLI (argparse validates ACCESSION,FORM,STORAGE_PATH
structure; form values are filtered by ADV allowlist in `adv_bronze_discovery.py`).

---

## Sources

### Primary (HIGH confidence)
- Codebase: `edgar_warehouse/application/warehouse_orchestrator.py` — `_run_parse_adv_bronze` at line 1821 [VERIFIED: codebase]
- Codebase: `edgar_warehouse/application/adv_bronze_discovery.py` — discovery contract [VERIFIED: codebase]
- Codebase: `edgar_warehouse/mdm/cli.py` — `_REQUIRED_TABLES_RUN` at line 340-361 [VERIFIED: codebase]
- Codebase: `edgar_warehouse/infrastructure/warehouse_settings.py` — command classification [VERIFIED: codebase]
- Live S3 query: `sec_company_filing WHERE form LIKE 'ADV%'` → 0 rows out of 2,858,889 [VERIFIED: live silver.duckdb + shard-0.duckdb]
- Live S3 query: `sec_adv_filing` → 0 rows [VERIFIED: both silver.duckdb and shard-0.duckdb]
- Phase 5 CONTEXT.md: D-10, D-14, D-16 decisions [VERIFIED: `.planning/workstreams/neo4j-pipe/phases/05-source-to-mdm-load-path/05-CONTEXT.md`]
- STATE.md / REQUIREMENTS.md: locked constraints [VERIFIED: `.planning/workstreams/neo4j-pipe/STATE.md` and `REQUIREMENTS.md`]

### Secondary (MEDIUM confidence)
- `docs/aws-mdm-source-to-mdm.md` — existing operator runbook (Phase 5 Plan 05-04 output) — confirmed no `parse-adv-bronze` step exists

### Tertiary (LOW confidence)
- A1 in Assumptions Log: EDGAR submissions.json path for investment adviser ADV filings — not verified, requires one real CIK lookup to confirm [ASSUMED]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all components verified in Phase 9 codebase
- Architecture: HIGH — live S3 and codebase verified
- Pitfalls: HIGH — root cause confirmed by live data queries
- Precondition gap: HIGH — 0/0/0/0 ADV rows confirmed across main silver AND shard-0
- Fork decision: User input required — not a research determination

**Research date:** 2026-06-04
**Valid until:** 2026-07-04 (30-day window; stable codebase, S3 state changes only if bootstrap runs)

---

## Appendix: IAPD Findings (Fork A — Extended)

**User decision:** Fork A (extended) — build minimal IAPD ingestion to obtain one ADV filing, store as S3 bronze, run full live validation. User explicitly approved relaxing the "no SEC fetch" constraint for this one-time bootstrap.

### Confirmed: ADV Forms Are NOT in EDGAR

Verified definitively during research:
- `edgar EFTS search (forms=ADV, all of 2024)` → `0 hits`
- Goldman Sachs CIK 886982 `submissions.json` → 0 ADV form types (only 10-K, 10-Q, 13F-HR, 3, 4, etc.)
- ADV forms are processed through IARD (Investment Adviser Registration Depository), a separate FINRA-operated system

**Consequence:** `edgar-warehouse bootstrap --cik-list <adviser_cik>` will NOT capture ADV bronze. Standard EDGAR bootstrap is the wrong tool for ADV data.

### IAPD Data Source

ADV form data for the current period is available via:
1. **IAPD website**: `https://adviserinfo.sec.gov/adv` — individual firm ADV filings, browser-based
2. **IAPD Search API**: `https://api.adviserinfo.sec.gov/search/firm?query=...&nrows=N&start=0&wt=json` — publicly accessible, no auth required
3. **SEC bulk CSV data**: Historical pre-2025 ADV Part 1 structured CSV files — available at `https://www.sec.gov/open/datasets/form-adv.json` (URL format not confirmed due to rate limiting)

**IAPD Firm-specific API** (e.g., `/firm/{crd}/iapd/AdvFiling`) returns `403 Forbidden` — requires browser session or auth.

**edgartools** has NO IAPD module. No built-in ADV fetch capability.

### Target Investment Adviser

| Field | Value |
|-------|-------|
| Name | VANGUARD GROUP INC |
| CRD (firm_source_id) | 105958 |
| SEC File Number | 801-11953 |
| Scope | ACTIVE |
| Source | IAPD Search API — confirmed active |

### Ingestion Path for Fork A

The `--artifact` explicit path in `parse-adv-bronze` allows bypassing the `sec_company_filing` registry entirely:

```bash
edgar-warehouse parse-adv-bronze \
  --artifact "ACCESSION,ADV,s3://edgartools-dev-bronze-077127448006/warehouse/bronze/filings/sec/cik={CIK}/accession={ACCESSION}/primary_doc.xml,{CIK}"
```

Where `storage_path` is an S3 URI pointing to an ADV XML file that was uploaded manually or via a one-time script.

**Proposed execution sequence for Fork A:**
1. Obtain one ADV XML filing for a known investment adviser (Vanguard CRD 105958 or similar)
   - Option A: Use IAPD browser download (requires Chrome automation or manual step)
   - Option B: Use SEC bulk CSV → convert to minimal XML the parser can process
   - Option C: Find a direct IAPD download URL at execution time via network inspection
2. Upload to S3 at `s3://edgartools-dev-bronze-077127448006/warehouse/bronze/filings/sec/cik={CIK}/accession={ACCESSION}/primary_doc.xml`
3. Run: `edgar-warehouse parse-adv-bronze --artifact "..."`
4. Verify `sec_adv_filing` > 0 rows (MDM-ADV-01)
5. Run: `edgar-warehouse mdm run --entity-type adviser` (MDM-ADV-02)
6. Update `docs/aws-mdm-source-to-mdm.md` (MDM-ADV-03)

### ADV XML Format Accepted by Parser

From `edgar_warehouse/parsers/adv.py` (verified): the parser accepts:
- XML with `<edgarsubmission>`, `<advfiling>`, or generic `<xml>` root tags
- HTML with `<body>` / `<table>` / `<html>` tags
- Plain text
- PDF

For a one-time test fixture, a minimal XML in the format:
```xml
<advFiling>
  <advisorName>Vanguard Group Inc</advisorName>
  <secFileNumber>801-11953</secFileNumber>
  <crdNumber>105958</crdNumber>
  <effectiveDate>2024-01-15</effectiveDate>
  <offices><office><city>Malvern</city><state>PA</state></office></offices>
</advFiling>
```
would satisfy the parser (the `<advfiling>` tag triggers XML parsing mode). However, using real IAPD XML is strongly preferred to ensure the full pipeline (S3 read → parse → silver write) handles real-world data.

### Pitfall 6: IAPD API Requires Auth for Firm-Specific Endpoints
**What goes wrong:** Calling `/firm/{CRD}/iapd/AdvFiling` returns `403 Forbidden`. The IAPD individual firm API is not publicly accessible via simple HTTP GET.
**How to avoid:** Use the IAPD website via browser (Chrome automation), or use SEC bulk CSV data, or use a minimal test XML.
**Warning signs:** `{"message":"Forbidden"}` response from `api.adviserinfo.sec.gov/firm/...`
