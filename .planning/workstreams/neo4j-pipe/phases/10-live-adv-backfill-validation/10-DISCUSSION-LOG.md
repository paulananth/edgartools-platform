# Phase 10: Live ADV Backfill Validation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-04
**Phase:** 10-Live ADV Backfill Validation
**Areas discussed:** Run scope, Fund preflight, Success criteria, Evidence format, Local vs ECS execution, MDM Postgres availability, Silver DuckDB location, Phase 5 resume scope, Environment setup, Failure testing

---

## Run Scope

| Option | Description | Selected |
|--------|-------------|----------|
| `--limit 50` | Fast sample, proves pipe works, easy to re-run | ✓ |
| `--limit 200` | Larger sample covering more form variants | |
| Full corpus (no `--limit`) | Processes all ADV accessions, definitive but slow | |

**User's choice:** `--limit 50` sample only; full corpus is a separate operator task.

| Option | Description | Selected |
|--------|-------------|----------|
| First 50 alphabetically | Default behavior, no `--accession-list` | |
| Target specific accessions | Pre-select via silver query | ✓ |

**User's choice:** Target specific accessions via `--accession-list`.

| Option | Description | Selected |
|--------|-------------|----------|
| Query silver for advisers with funds | Join sec_company_filing → raw_objects, top-CIK by count | ✓ |
| Hardcode known fund-manager CIKs | Requires SEC lookup | |
| You decide | Claude picks during execution | |

**User's choice:** Query silver — `SELECT cik, COUNT(*) FROM sec_company_filing WHERE form IN ('ADV','ADV/A') GROUP BY cik ORDER BY COUNT(*) DESC LIMIT 5`.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, pre-filter via storage_path check | JOIN to raw_objects WHERE storage_path IS NOT NULL | ✓ |
| No, let parse-adv-bronze handle it | Run unfiltered, check event log for missing-artifact count | |

**User's choice:** Pre-filter to guarantee all 50 accessions have confirmed S3 artifacts.

---

## Fund Preflight

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 10 fails if sec_adv_private_fund empty | Strict: both tables must have rows | |
| Adviser preflight is enough; fund is best-effort | sec_adv_filing nonzero = pass | |
| Explicitly include a known fund-manager CIK | Hardcode 1-2 large fund-adviser CIKs | ✓ |

**User's choice:** Use top-5-by-ADV-count CIKs from silver — high-volume filers are almost always large advisers managing private funds.

| Option | Description | Selected |
|--------|-------------|----------|
| Both adviser and fund MDM runs | Both exit 0 = Phase 10 complete | ✓ |
| Adviser only | Fund deferred to later run | |
| Single `--entity-type all` | Does NOT enforce adviser/fund tables nonempty | |

**User's choice:** Both `mdm run --entity-type adviser` AND `mdm run --entity-type fund` must pass.

| Option | Description | Selected |
|--------|-------------|----------|
| Actual write to MDM Postgres | Proves data lands in MDM end-to-end | ✓ |
| Preflight check only (dry-run) | Safe if Postgres unavailable | |
| You decide | Claude picks based on availability | |

**User's choice:** Actual write to MDM Postgres.

---

## Success Criteria

| Option | Description | Selected |
|--------|-------------|----------|
| Any nonzero rows in sec_adv_filing | Minimal bar | ✓ |
| Rows >= 90% of sample size | Stricter threshold | |
| Zero parse errors required | Strictest — any error fails | |

**User's choice:** Any nonzero rows in `sec_adv_filing` (and `sec_adv_private_fund` via fund-manager CIK selection).

| Option | Description | Selected |
|--------|-------------|----------|
| Parse errors acceptable up to 20% | Up to 10 of 50 errors OK | |
| Parse errors are warnings only | Phase passes regardless of error count | |
| Zero parse errors required | All 50 must parse cleanly | ✓ |

**User's choice:** Zero parse errors. Any error → investigate and fix before Phase 10 done.

| Option | Description | Selected |
|--------|-------------|----------|
| Investigate and fix before marking done | Treat any error as a blocker | ✓ |
| Swap failing accessions for others | Replace data-specific failures | |
| You decide | Claude picks remediation path | |

**User's choice:** Investigate and fix. Swapping accessions acceptable only if error confirmed data-specific (not a parser bug).

**Full success gate (all must pass):**
- `parse_adv_bronze_completed` with `errors=0`
- `sec_adv_filing` rows > 0
- `sec_adv_private_fund` rows > 0
- `mdm run --entity-type adviser` exits 0 + `mdm_adviser` rows > 0
- `mdm run --entity-type fund` exits 0 + `mdm_fund` rows > 0
- `backfill-relationships` exits 0
- `sync-graph` exits 0
- `verify-graph` exits 0

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, verify MDM rows written | SELECT COUNT(*) FROM mdm_adviser/mdm_fund | ✓ |
| Exit code 0 is sufficient | Trust exit 0 means rows written | |
| You decide | Claude checks if it seems useful | |

---

## Evidence Format

| Option | Description | Selected |
|--------|-------------|----------|
| Validation notes doc in phase dir | 10-VALIDATION-NOTES.md with full evidence | ✓ |
| Update STATE.md only | Minimal, no separate artifact | |
| New automated test | pytest + fixtures for ADV XML | |

**User's choice:** `10-VALIDATION-NOTES.md` with selection query + accession list, parse-adv-bronze command + terminal output, silver row counts, MDM commands + Postgres row counts, and relationship pipeline outcomes.

**User note:** "use edgartools for parsing" — confirms ADV parsing uses `edgartools` package via `edgar_warehouse/parsers/adv.py`. No change to parser.

| Option | Description | Selected |
|--------|-------------|----------|
| Include completion declaration + Phase 5 resume pointer | End notes with COMPLETE declaration and next steps | ✓ |
| Just the validation data | Pure data record | |

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, update STATE.md too | Phase 10 status → Complete with row count summary | ✓ |
| VALIDATION-NOTES.md only | STATE.md update not in scope | |

---

## Local vs ECS Execution

| Option | Description | Selected |
|--------|-------------|----------|
| Local CLI run | edgar-warehouse on dev machine, dev S3 env vars | ✓ |
| ECS task via Step Functions | More production-representative, slower iteration | |
| You decide | Claude picks based on availability | |

---

## MDM Postgres Availability

| Option | Description | Selected |
|--------|-------------|----------|
| Local Colima Postgres | MDM_DATABASE_URL=postgresql://postgres:test@localhost:5432/mdm | ✓ |
| VPC dev Postgres | Requires VPN or port-forwarding | |
| You decide | Claude uses whatever available | |

---

## Silver DuckDB Location

| Option | Description | Selected |
|--------|-------------|----------|
| Pulled from WAREHOUSE_STORAGE_ROOT (S3 sync'd local) | CLI syncs before reads/writes | ✓ |
| Purely local file at fixed path | Not in S3 | |
| You decide | Claude inspects warehouse config | |

---

## Phase 5 Resume Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Out of Phase 10 scope — Phase 5 resume separate | Phase 10 ends at MDM rows written | |
| Phase 10 includes running relationship pipeline | backfill-relationships → sync-graph → verify-graph | ✓ |
| You decide | Claude determines how far to take it | |

**User's choice:** Phase 10 includes the full relationship pipeline through Neo4j verify-graph.

| Option | Description | Selected |
|--------|-------------|----------|
| Local Colima Neo4j | NEO4J_URI=bolt://localhost:7687 | ✓ |
| Dev VPC Neo4j | Requires VPN or SSH tunnel | |
| You decide | Claude picks based on availability | |

---

## Environment Setup Steps

| Option | Description | Selected |
|--------|-------------|----------|
| Include startup steps | colima start, docker run for Postgres and Neo4j | ✓ |
| Assume already running | Add preflight check note only | |
| docker-compose reference | Point to existing compose file | |

| Option | Description | Selected |
|--------|-------------|----------|
| Raw docker run commands | Document explicit commands, no new file | ✓ |
| Create docker-compose.yml as part of Phase 10 | Adds deliverable to Phase 10 scope | |

---

## Failure Testing and Remediation

**User selection:** All three failure scenarios in scope.

1. **parse-adv-bronze parse errors** — Investigate and fix parser before Phase 10 done. Swap data-specific failures only.
2. **backfill-relationships / sync-graph failures** — Check Neo4j connectivity, inspect error, fix root cause, re-run. Document retry.
3. **Deliberate failure test step** — Pass a known-bad artifact (`--artifact FAKE-ACCESSION-0,ADV,s3://invalid-path/fake.xml`) and verify non-fatal error event is emitted while run continues.

---

## Claude's Discretion

- If a parse error is investigated and confirmed data-specific (not a parser bug), Claude may swap the failing accession for another from the same CIK's filing list.
- Claude infers Neo4j container startup command from standard Neo4j Docker image if no existing script is found.

## Deferred Ideas

- Full corpus ADV run (all accessions, no `--limit`) — separate operator task after validation
- `docker-compose.yml` for local Postgres + Neo4j — future phase
- Phase 5 full-scale graph sync for entire adviser/fund universe — Phase 5 resume (Phase 10 covers 50-accession sample only)
- Automated pytest regression test with ADV XML fixtures — deferred due to fixture overhead
