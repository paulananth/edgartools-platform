# Handoff to Claude — 2026-07-26

**From:** Grok residual-holds / wayfinder / gold SOURCE session  
**Repo:** `edgartools-platform` · branch **`main`** @ `be4abfe` (after #271)  
**AWS account:** `690839588395` · region `us-east-1` · env **prod**

Do **not** self-declare production GO. Do **not** redrive Step Functions after image changes (start new execution names). Prefer `claude/<topic>` branches for commits.

---

## 1. Residual holds (primary in-flight)

### Outcome

| Item | Status |
| --- | --- |
| Residual MDM fill (security, person, IS_INSIDER, HOLDS, COMPANY_HOLDS) | **Done** in Postgres |
| INSTITUTIONAL_HOLDS | **Still 0** in MDM (open investigation) |
| Graph candidate | **`residual-full-20260726T010010Z`** — **verified** (193,323 nodes / **166,067** edges) |
| Active graph pointer | **Unchanged** — still Ticket 20 gen |
| Production GO | **Not declared** |

**Active generation:**  
`ticket20-strict-endpoint-seal-850ea34-20260725T130457Z` (193,063 nodes / 157,732 edges — EMPLOYED_BY + MANAGES_FUND only)

**Verified candidate (not activated):**  
`residual-full-20260726T010010Z`  
- Edges match MDM total 166,067 including HOLDS 5,253 · COMPANY_HOLDS 1,778 · IS_INSIDER 1,304 · security nodes 97

### Failed run (do not redrive)

- `residual-holds-20260725T222735Z` — FAILED at `MdmVerify`
- Root cause: type-filtered sync + verify without `--generation-id` checked **active** vs full MDM
- Incomplete candidate `69e139b0-f4d4-46bf-b4f2-0f69571e2277` — **do not activate**

### Fix shipped

| PR | What |
| --- | --- |
| #266 | mdm-large 8 GiB after MdmSecurities OOM |
| #270 | residual SM: full `sync-graph` + `verify-graph --generation-id $$.Execution.Name` |
| #271 | status evidence doc |

**Evidence:** `docs/release-readiness/residual-holds-status-2026-07-26.md`  
**Operator doc:** `docs/release-readiness/residual-holds-graph-pipeline.md`

### Operator next (activation — explicit human go only)

```bash
# Only if Release Owner wants residual candidate live:
mdm graph-activate --generation-id residual-full-20260726T010010Z
```

Until then, agents/dashboard on active pointer still see **no** HOLDS/IS_INSIDER/security on the live generation.

### Open residual bug

- **INSTITUTIONAL_HOLDS = 0** after derive step reported OK — check derive eligibility, silver 13F windows, export, limits (`--target-per-type 50000`).

---

## 2. Gold SOURCE / COMPANY empty (fixed)

| Issue | Fix |
| --- | --- |
| `GOLD.COMPANY` empty | Native pull aborted: missing SOURCE tables + `EARNINGS_CALENDAR` not in load map |
| Applied in prod | Created `SEC_SUBSIDIARY_EVIDENCE`, `SEC_AUDITOR_REPORT_EVIDENCE`, `SEC_EMPLOYMENT_EVENT`, `EARNINGS_CALENDAR`; patched `LOAD_EXPORTS_FOR_RUN` |
| Reloaded | Ticket 20 gold_refresh run → **SOURCE/GOLD.COMPANY = 32,968** |
| Repo | **#267** bootstrap + load procedure |

**Not a duplicate of `GOLD.MDM_COMPANY`:** warehouse dim (CIK) vs MDM export (entity_id). Option B design to unify — see below.

---

## 3. Unified company dimension (Option B) — design only

**Map:** `.scratch/unified-company-dimension/`

| Decision | Choice |
| --- | --- |
| PK | `company_key` / CIK |
| Name | `EDGARTOOLS_GOLD.COMPANY` |
| MDM_COMPANY | compat view → drop after soak |
| Join | left join MDM; multi-match pick+flag |
| Agent surface | CIK only (no entity_id as Decision Feature) |
| Implement | ticket **05** open — **claim before coding** |

PR **#268** landed the grilling map.

---

## 4. Wayfinder release-readiness hygiene

**PR #269**

- Dual ticket 21 renumbered: insider → **24**; ADV private-fund stays **21**
- Ticket 24 **resolved** (10-CIK IS_INSIDER 146/146); GO separate
- Full-Chain Launch Gate unblocked from stale 20–23
- Map Decisions so far refreshed for 16–24

**Release-readiness frontier (grill/prototype, not bulk-load re-run):**

1. Rollback Rehearsal Contract (05)  
2. Full-Chain Launch Gate (06)  
3. Release-Bound Dashboard Acceptance (07)  
4. Release Evidence Automation (09)  
5. Direct-Evidence GO Packet (08) — blocked by 05, 06, 07, 09  

**ADV pipeline frontier:** grill ticket 02 (fetch/rolling window) — `.scratch/adv-pipeline/`

---

## 5. Cleaned up local junk

Deleted (fully merged / content on main):

- Worktree + branch `agent/grok-ticket21-insider-sm`
- Worktree + branch `research/adv-iapd-format-scope`

---

## 6. Prod images / deploy notes

- MDM image in use: `…/edgartools-prod-mdm@sha256:4e47c2ece8…`  
- Warehouse: `…/edgartools-prod-warehouse@sha256:a8eb79a3…`  
- `mdm-large` exists (8 GiB); residual heavy stages use it  
- Account `690839588395` only; `077127448006` is decommissioned  

Deploy app (task defs + SMs, skip build) pattern already used:

```bash
bash infra/scripts/deploy-aws-application.sh \
  --env prod --aws-account-id 690839588395 --aws-region us-east-1 \
  --skip-build \
  --image-ref '<warehouse digest ref>' \
  --mdm-image-ref '<mdm digest ref>' \
  --enable-mdm --mdm-database-source snowflake-postgres \
  --output-file infra/aws-prod-application.json
```

---

## 7. Suggested next moves for Claude

**Priority order agreed with operator:**

1. ~~Residual holds to verify~~ — **done** (candidate verified; activation = human)  
2. **If product wants residual live:** graph-activate `residual-full-20260726T010010Z` after explicit go  
3. **GO planning:** release-readiness 05 or 06 grill  
4. **Optional implement:** ER Catalyst Board (er-dashboards 05) or claim unified COMPANY 05  
5. **Investigate INSTITUTIONAL_HOLDS = 0** if holdings completeness matters for GO  

---

## 8. Do not

- Claim Ticket 20 / residual as **GO**  
- Activate incomplete gen `69e139b0…`  
- Redrive failed residual executions after SM/image changes  
- Re-run Ticket 20 bulk-load from zero without operator decision  
- Commit to branches owned by the other runtime without handoff  

---

## Key paths

| Need | Path |
| --- | --- |
| Residual status | `docs/release-readiness/residual-holds-status-2026-07-26.md` |
| Residual SM design | `docs/release-readiness/residual-holds-graph-pipeline.md` |
| Ticket 20 completion | `docs/release-readiness/ticket20-completion-2026-07-25.md` |
| Ticket 21 insider sample | `docs/release-readiness/ticket21-insider-coverage-10cik-2026-07-25.md` |
| Release readiness map | `.scratch/release-readiness/map.md` |
| Unified COMPANY design | `.scratch/unified-company-dimension/` |
| ADV pipeline map | `.scratch/adv-pipeline/map.md` |
