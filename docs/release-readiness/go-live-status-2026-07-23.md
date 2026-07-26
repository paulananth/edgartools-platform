# Go-Live Status — 2026-07-23

**Placement note:** this file lives in `docs/release-readiness/` alongside
`ticket20-strict-bulk-load-resume.md`, `required-relationship-bulk-load-completion-gate.md`,
and the other gate-definition docs — the established convention in this repo for
committed, citable release-readiness state (as opposed to `.scratch/release-readiness/`,
which holds the working wayfinder ticket, or `.planning/`, which holds GSD workstream
mechanics). No better-established convention was found during this investigation.

## Current status (read this first)

**"Go-live" means two different, non-overlapping things in this repo, and only one of
them is done:**

| Meaning | Scope | Status |
|---|---|---|
| **Production Operator Readiness** — infra deploy/verify/monitor/recover mechanics (`infra/scripts/go-live.sh`, the `.planning/workstreams/go-live/` v1.6 GSD milestone) | AWS Terraform, Snowflake stack, ECR/ECS, dbt gold, MDM+graph *connectivity*, dashboard, bounded smoke | **DONE.** GO recorded 2026-06-26 UTC, 12/12 v1.6 requirements complete (`.planning/workstreams/go-live/ROADMAP.md:1-31`, `STATE.md` tail). |
| **"Current-Head Production Launch Readiness"** (formal term, `CONTEXT.md:137-139`) — decision-complete evidence that a specific release candidate's *data* (not just infra) is safe to call GO, currently instantiated as **Ticket 20** (the required-relationship strict bulk load) | `EMPLOYED_BY` + `INSTITUTIONAL_HOLDS` relationship bulk-load completeness, Bulk-Load Completion Ledger, exact MDM-to-graph parity | **NOT DONE. NO_GO.** Actively running (`ticket20-strict-1yr-retry6-20260722T200844Z`, `RUNNING`, 18/110 `StrictBatchSilver` batches succeeded as of 2026-07-23T10:10 UTC — see §5). |

`infra/scripts/go-live.sh` does **not** invoke Ticket 20's strict/`release_mode` path at
all — its own `bronze_seed_silver_gold` stage explicitly uses the ordinary (non-strict,
skip-artifact-capable) chain (`infra/scripts/go-live.sh:698-731`). The two "go-lives" are
tracked in different places (`.planning/workstreams/go-live/` vs.
`.scratch/release-readiness/issues/20-...md` + `docs/release-readiness/*.md`) and use
different vocabularies. Treat a claim of "go-live is done" as ambiguous until the asker
specifies which one.

**What's blocking right now:**

1. **Ticket 20 itself is unfinished and mid-execution.** The freeze (125,819 candidates /
   12,444 CIKs) has had 6 strict-load attempts since 2026-07-18, all but the current one
   FAILED for distinct root causes (§5). The currently running attempt (`retry6`) is
   pinned to the pre-PR#234/#235/#236 image (it started before those fixes were promoted
   to prod) and is projected — not yet observed — to hit the pre-fix MDM/graph bugs when
   it reaches that stage, days from now at current batch rate.
2. **A real, but separate, contradiction in the operator record**: the wayfinder ticket
   (`.scratch/release-readiness/issues/20-execute-required-relationship-production-bulk-load.md:8-15`)
   says Ticket 20 is "**ON HOLD (2026-07-20)**" pending the Company Identity Pipeline map,
   and that map's own notes (`.scratch/company-master-pipeline/map.md:35-43`) reaffirm the
   hold in the same words. Yet AWS Step Functions shows **six** strict executions
   launched *after* 2026-07-20 (`ticket20-strict-1yr-20260721T125703Z` through
   `-retry6-20260722T200844Z`, §5). Either the hold was informally lifted by direct
   operator action without updating either doc, or the docs are stale. This report does
   not resolve which — it is a real open discrepancy, not an assumption made here.
3. **The three PRs landed this session (#234–236) fixed *activation machinery*, not
   Ticket 20 load completion.** The user's manually-validated prod state (112 MDM
   entities, 1 `MANAGES_FUND` relationship, 112 graph nodes / 1 edge, exact parity) has
   **zero `EMPLOYED_BY` and zero `INSTITUTIONAL_HOLDS` edges** — the two relationship
   types Ticket 20 exists to bulk-load and prove parity for
   (`docs/release-readiness/required-relationship-bulk-load-completion-gate.md:9-13`).
   The fixes make the sync→verify→activate pipeline *work* for the first time; they do
   not constitute progress on the bulk-load itself.
4. **A second, unrelated gate is also open**: the gated daily EventBridge schedule for
   `daily-incremental` (PR #233, merged) exists in Terraform but has **not been applied
   to prod** — confirmed live: `aws events list-rules --name-prefix edgartools` returns
   zero rows (§5). `.scratch/todos-close-out/map.md:33` already flags this needs the same
   kind of explicit operator go-ahead as Ticket 20.

**What's next:** let `retry6` either reach `SUCCEEDED` (unlikely to matter — it's pinned
to pre-fix code and will very likely fail at the MDM/graph tail per its P3 pinning) or
`FAILED`/`ABORTED`; per the ticket20-strict-bulk-load-resume.md P3 rule, do **not** redrive
it — start a fresh execution on the post-#236 image once it terminates. Separately, decide
whether the 2026-07-20 hold is still in force before doing so (item 2 above).

---

## 1. What "go-live" means in this repo, formally

Two independent things share the word informally; only one has a name in the formal
glossary.

- **`infra/scripts/go-live.sh`** is an interactive wizard/CLI (`wizard|doctor|init|plan|deploy|report`)
  that walks an operator through provisioning and deploying **one environment's** full
  stack: AWS Terraform state bucket → passive infra → access roles → ECR image publish
  (warehouse + MDM) → ECS task defs/Step Functions → Snowflake native-pull foundation →
  dbt gold → Streamlit dashboard → Snowflake Postgres/graph prerequisites → a
  `bronze_seed_silver_gold` one-click data refresh (ordinary chain, not Ticket 20's
  strict path) → MDM+graph connectivity/sync/verify → AWS MDM E2E/status checks →
  bounded data smoke (`infra/scripts/go-live.sh:601-754`). It is preview-first by
  default; `--apply` gates every stage behind a per-stage confirmation
  (`infra/scripts/go-live.sh:844-883`). Nowhere in this script does "Ticket 20",
  "release_mode", "strict", or "relationship_release" appear — confirmed by reading the
  full file (991 lines). Its scope is squarely **Production Operator Readiness**: can an
  operator deploy, verify, monitor, and recover the stack — not "is the data behind it
  release-complete."
- **`.planning/workstreams/go-live/`** is the GSD workstream that operationalized exactly
  that scope as v1.6 and reached a recorded **GO on 2026-06-26 UTC**
  (`.planning/workstreams/go-live/ROADMAP.md`: "**Next Step:** None required to launch —
  v1.6 is shipped and GO"). All 5 tracked blockers (dashboard UAT, hosted-graph E2E,
  Neo4j runtime remnants, MaxConcurrency=4 evidence, final sign-off) are recorded
  FULLY REMEDIATED (`.planning/workstreams/go-live/STATE.md` tail). One explicitly
  non-blocking follow-up remains open (upgrading GRAPH-04's "accepted basis" to a fully
  verified MaxConcurrency=4 run) — the doc itself calls this optional and states "No
  further phases are planned in this workstream."
- **`CONTEXT.md:137-139`** defines the broader, decision-complete idea as
  **"Current-Head Production Launch Readiness"**: *"The decision-complete evidence state
  for deploying an identified current release candidate through the production operator
  path."* Its `_Avoid_` line explicitly warns against confusing it with "Historical
  go-live status" or "public launch readiness" — i.e., this term is deliberately broader
  than the infra-only wizard and deliberately narrower than a customer launch. This is
  the formal term whose current concrete instance is Ticket 20: the completion-gate doc
  states plainly that "Production GO remains blocked until tasks 16–20 ... are
  implemented and a production evidence artifact passes"
  (`docs/release-readiness/required-relationship-bulk-load-completion-gate.md:7`).
  `CONTEXT.md:273-275` separately defines **"Public Launch Readiness"** (customer-facing
  access/support/policy) as explicitly **out of scope** for either of the above.

**Conclusion for Q1:** `go-live.sh` is scoped to the narrower, already-completed
Production Operator Readiness meaning. The broader "Current-Head Production Launch
Readiness" gate is a separate, still-open concept whose current blocking instance is
Ticket 20 — the two are related (Ticket 20 runs *through* the infra go-live.sh
provisioned) but not the same gate, and `go-live.sh` was never wired to check or invoke
Ticket 20's strict path.

## 2. Ticket 20 status per `docs/release-readiness/ticket20-strict-bulk-load-resume.md`

Read in full (147 lines). It is an **operator resume runbook**, not itself a
done/pending tracker — it defines mechanics for continuing after a failure, not Ticket
20's overall disposition (that lives in the wayfinder ticket and the completion-gate
doc, §3 below). Key content:

- **P3 rule (headline, lines 1-20):** never redrive a failed `bronze_seed_silver_gold`
  execution after deploying a new image/task-def — AWS redrive pins the old task-def
  revision. Always start a **new execution name** after any image/code change.
- **Strict freeze gate (lines 22-51):** `bootstrap-batch --release-mode` and
  `reconcile-relationship-release` reject candidate manifests lacking
  `coverage_by_document_type` or declaring windows outside the locked agent lookbacks
  (13F `max(W−3y, 2013-05-20)`, proxy `W−5y`, Item 5.02 8-K `W−2y`).
- **P0/P1/P2 resume mechanics (lines 84-125):** batch-level (`batch_done/{batch_identity}.json`)
  and accession-level (`accession_done/{accession}.json`) idempotency markers so a
  resumed run skips already-terminal work; progress events every 100 accessions.
- **End-to-end resume checklist (lines 126-140)**: after map success,
  `reconcile-relationship-release` writes `bulk-load-completion-ledger.json` and
  `required_relationship_bulk_load_evidence.json` (PASS disposition + fingerprint +
  watermark + `coverage_by_document_type` + terminal counts).
- Explicitly **not** in scope of "resume": `artifact_policy=skip` (invalid for Ticket 20
  GO), silently skipping SEC forever, or redrive-after-image-change (line 141-146).

This doc assumes readers already know Ticket 20's substantive done/pending state, which
lives in two other places:

- **`docs/release-readiness/required-relationship-bulk-load-completion-gate.md`** (298
  lines, read in full) is the semantic/architectural gate definition: what `EMPLOYED_BY`
  and `INSTITUTIONAL_HOLDS` mean, the document-type-specific coverage windows, the
  Bulk-Load Completion Ledger schema, six hard checks (candidate inventory, artifact
  capture, parsing/silver publication, workflow behavior, MDM applicability, graph
  proof), retry/repair policy, and the approved PASS/GO claim language. It records (as of
  its last edit) that "the current implementation does **not** pass it" and that GO is
  blocked pending tasks 16-20 (`required-relationship-bulk-load-completion-gate.md:7`).
  It also documents a **2026-07-19 Release Owner decision** accepting a bounded,
  enumerated Item 5.02 `unresolved` gap (~9.5% of Item 5.02 candidates) rather than
  requiring 100% NLP resolution — with the caveat that the *mechanism* to enforce/enumerate
  that bounded exception was, as of this doc, still "pending, not yet built"
  (`required-relationship-bulk-load-completion-gate.md:224-234`).
- **`.scratch/release-readiness/issues/20-execute-required-relationship-production-bulk-load.md`**
  (last edited 2026-07-20) is the live wayfinder ticket tracking actual attempt history —
  see §3.

## 3. Ticket 20 wayfinder ticket — attestations and current disposition

Read `.scratch/release-readiness/issues/20-execute-required-relationship-production-bulk-load.md`
in full (118 lines).

- **Status header:** `Type: task`, `Status: open`, **"ON HOLD (2026-07-20, explicit
  operator decision): do not relaunch until the 'Company Identity Pipeline' wayfinder map
  ... has progressed far enough"** (lines 8-15). The hold is described as "a deliberate
  sequencing decision, not a blocker on Ticket 20's own readiness."
  `.scratch/company-master-pipeline/map.md:35-43` restates the same hold verbatim as of
  the same date, framed as "explicit operator decision (2026-07-20), overriding this
  map's original 'independent, standalone' framing."
  **This is in tension with live AWS state** — see §5 and the "Current status" section
  above: six strict executions started 2026-07-21 and 2026-07-22, after this hold was
  recorded, and neither doc has been updated to reflect a lift. Flagging this rather than
  resolving it.
- **"Done when" criteria (revised 2026-07-19 per Ticket 21, lines 27-42):** candidate
  inventory/ledger reconcile exactly; zero failure/quarantine/circuit-breaker-leftover/
  unapproved-force counts; Item 5.02 `unresolved_accepted` within the bounded, enumerated
  threshold; **zero unresolved insiders** (`mdm verify-insider-coverage`) as the actual
  EMPLOYED_BY completeness bar (non-insider executives are best-effort, non-gating); a
  no-change rerun with zero SEC network calls and identical semantic digests;
  `EMPLOYED_BY` exact MDM-to-graph parity (blocking); `INSTITUTIONAL_HOLDS` parity
  verified/reported but **non-blocking** per a 2026-07-19 Release Owner decision; and
  named Warehouse/MDM/Graph/Release Data Operator/Release Owner attestations bound to the
  evidence artifact.
- **Attestation mechanism — still current, not superseded.** The five named roles
  (`warehouse`, `mdm`, `graph`, `release_data_operator`, `release_owner`) plus a
  `candidate_fingerprint` remain exactly what
  `edgar_warehouse/scripts/build_ticket20_strict_execution_input.py` requires: its
  `--attestations-json` argument is `required=True` and documented as "JSON object with
  five named gate attestation roles" (`build_ticket20_strict_execution_input.py:47-51`,
  docstring lines 1-19). PR #235's new `--generation-id` flag on `mdm verify-graph`
  (`edgar_warehouse/mdm/cli.py:204`: *"Verify this candidate generation instead of the
  currently-active one"*) is **additive** — a graph-generation identity used internally
  by the new `StrictMdmVerifyCandidate`/`StrictMdmActivate` states
  (`infra/scripts/deploy-aws-application.sh:2564-2565`, confirmed live in this session) —
  not a replacement for the five-attestation gate.
- **Attempt history recorded in the ticket (as of 2026-07-20 edit, lines 61-92):** three
  distinct FAILED strict executions each with a different root cause (click/spaCy
  dependency; NULL 13F `report_date` into DuckDB; an edgartools XML-namespace bug
  silently returning zero 13F holding rows) — each is characterized as "a distinct root
  cause, not a repeat," consistent with the repo's stated fail-closed philosophy. The
  live AWS record (§5) shows three *more* attempts since the ticket file's last edit
  (`-1yr`, `-retry2` through `-retry6`), none of which are yet reflected back into this
  ticket file.

## 4. TODOS.md — other open go-live blockers

`TODOS.md` is 1,937 lines. Grepped for `go-live`, `go live`, `ticket 20`/`ticket20`,
`release readiness`, `blocker` (100 matches, reviewed in context). Findings:

- The dedicated close-out effort (`.scratch/todos-close-out/map.md`, last touched
  2026-07-22 13:20 — same day as this investigation) states it already reviewed
  `TODOS.md` in full: **"of ~26 entries, all but four are already
  RESOLVED/MITIGATED with evidence"** (`map.md:19-21`). The four open items are:
  1. `01-runtime-access-role-sharing-check.md` — resolved as "No" (prod/dev runner roles
     are namespaced apart, confirmed live via ECS task definitions), can close.
  2. `02-seed-universe-ipo-detection-source.md` — resolved: no new detection code needed;
     the real gap is that `daily-incremental` isn't scheduled at all in prod. **The fix
     (a gated EventBridge schedule, PR #233) is built and merged but "not yet applied to
     prod (needs explicit go, same as Ticket 20's launch gate)"** (`map.md:33`) —
     confirmed live in §5: zero EventBridge rules exist for it.
  3. `03-seed-universe-active-signal-source.md` — resolved and merged
     (Form-15-deregistration demotion logic); takes effect once daily-incremental
     actually runs (tracked under item 2, not duplicated).
  4. `04-ci-dbt-live-snowflake-investment-decision.md` — a decision-only item (invest in
     CI-run dbt against live Snowflake); prerequisite (an `EDGARTOOLS_DEV_DEPLOYER` SELECT
     grant codified in Terraform) is still outstanding, but this is unrelated to Ticket
     20/go-live gating.
  - One additional item (`financial_derived` YoY tiebreaker) is explicitly *not* a
    wayfinder ticket — already decided and reconfirmed against "the Ticket 20
    anti-overclaim doctrine" (`map.md:25-30`).
- **No other open go-live blockers were found in `TODOS.md`** beyond what this session
  already fixed (PRs #234-236) and what Ticket 20/the daily-incremental schedule already
  track. The close-out map itself found nothing "not yet specified" or "out of scope"
  during its 2026-07-22 review (`map.md:37-44`).

## 5. Live-state cross-check (AWS)

All timestamps below are from live AWS CLI calls made during this investigation
(2026-07-23, times as noted; region `us-east-1`, account `690839588395`).

**`edgartools-prod-bronze-seed-silver-gold` executions** (`aws stepfunctions list-executions`, 10 most recent):

| Execution | Start | Status |
|---|---|---|
| `ticket20-strict-1yr-retry6-20260722T200844Z` | 2026-07-22T16:08:47-04:00 | **RUNNING** |
| `ticket20-strict-1yr-retry5-20260722T114624Z` | 2026-07-22T07:46:26-04:00 | FAILED |
| `ticket20-strict-1yr-retry4-20260722T105728Z` | 2026-07-22T06:57:34-04:00 | FAILED |
| `ticket20-strict-1yr-retry3-20260722T013811Z` | 2026-07-21T21:38:13-04:00 | FAILED |
| `ticket20-strict-1yr-retry2-20260722T010743Z` | 2026-07-21T21:07:45-04:00 | FAILED |
| `ticket20-strict-1yr-20260721T125703Z` | 2026-07-21T08:57:12-04:00 | FAILED |
| `ticket20-strict-insider2-20260721T111853Z` | 2026-07-21T07:19:03-04:00 | ABORTED |
| `ticket20-strict-insider-20260720T020331Z` | 2026-07-19T22:03:33-04:00 | FAILED |
| `ticket20-strict-gatev2-20260719T135202Z` | 2026-07-19T09:52:12-04:00 | FAILED |
| `ticket20-strict-agent-20260718T225510Z` | 2026-07-18T20:56:27-04:00 | FAILED |

This confirms the ticket's own attempt log (§3) is stale by at least 6 executions —
`-1yr` through `-retry6` postdate the ticket file's last edit. It also confirms this has
been a persistently failing pipeline (9 of the last 10 named attempts FAILED/ABORTED, one
per session's stated distinct-root-cause philosophy) rather than a single clean run.

**`retry6` map-run progress** (`aws stepfunctions describe-map-run`, checked
2026-07-23T10:10 UTC): `succeeded: 18, running: 2, pending: 90, failed: 0, total: 110`.
This is later/further along than the 5/110 snapshot cited in this session's setup context
(~2026-07-22T22:12 EDT / 2026-07-23T02:12 UTC) — consistent with a genuinely slow,
multi-day `StrictBatchSilver` map, not a stall. At the observed rate (~13 batches over
~8 hours), the remaining 92 pending/running batches project to roughly 2+ more days
before this execution reaches its MDM/graph tail — where, per the session's setup
context, it is expected (not yet confirmed, since it hasn't gotten there) to hit the
pre-#234/#235/#236 bugs, because it started 2026-07-22T20:08 UTC and the fixes were
deployed to prod at approximately 2026-07-23T02:10 UTC per this session's own account —
that deploy time was not independently re-verified against a CI/deploy log by this
investigation and is taken as given from the task context.

**Other prod state machines** (`aws stepfunctions list-executions --status-filter
RUNNING`, checked same time): zero RUNNING executions on `gold-refresh`, `load-history`,
`mdm-run`, `mdm-sync-graph`, `mdm-verify-graph`, `mdm-backfill-relationships`,
`silver-mdm-gold`, or `daily-incremental`. `ticket20-strict-1yr-retry6-...` is the only
currently-running execution relevant to go-live across the state machines checked.

**EventBridge rules** (`aws events list-rules` / `--name-prefix edgartools`): only an
AWS-managed `StepFunctionsGetEventsForECSTaskRule` exists; **zero** rules match
`edgartools`/`daily`. This confirms TODOS.md close-out item 2 (§4): PR #233's gated daily
schedule is merged in source and deployed to dev images via CI (`gh run list --workflow
deploy.yml` shows it built successfully 2026-07-22T17:21Z) but has not been Terraform-applied
to create the actual EventBridge rule in prod.

**GitHub state** (`gh pr list --state open`): zero open PRs. `gh run list --workflow
deploy.yml --limit 5`: last 5 runs (#233-#236 plus one docs PR) all `completed`/`success`,
confirming CI built and pushed dev images for all three PRs cited in this session's setup
context, most recently #236 at 2026-07-23T02:06:19Z. (CI's `deploy.yml` only builds/pushes
`:dev`-tagged images per `CLAUDE.md`'s Image Management section; it does not promote to
prod or register task definitions — this session's claim of prod promotion and deployment
is taken from the task context and not independently re-verified against ECR/ECS state by
this investigation.)

## 6. Explicit go-live checklists elsewhere in the repo

Grepped `docs/` and root Markdown for `go-live checklist`, `launch readiness`,
`production readiness`, `go-live gate` (case-insensitive). Hits:

- `docs/release-readiness/initial-findings.md:1` — titled "Current-Head Production
  Launch Readiness: Initial Findings"; line 11 explicitly scopes out "public or
  customer-facing launch readiness" as "a separate destination."
- `CONTEXT.md:137,139,273` — the glossary definitions already covered in §1.

No standalone "go-live checklist" document with a literal step-by-step list independent
of the two tracks above (v1.6 operator-readiness workstream, Ticket 20 gate doc) was
found. The closest thing to a single-page checklist is
`required-relationship-bulk-load-completion-gate.md`'s "Hard checks" section (six
numbered checks, §2 above) for the Ticket 20 track, and
`.planning/workstreams/go-live/ROADMAP.md`'s "Coverage" table (12/12 requirements,
already complete) for the operator-readiness track.

---

## Sources consulted

- `infra/scripts/go-live.sh` (991 lines, read in full)
- `docs/release-readiness/ticket20-strict-bulk-load-resume.md` (147 lines, read in full)
- `docs/release-readiness/required-relationship-bulk-load-completion-gate.md` (298 lines, read in full)
- `docs/release-readiness/ticket20-production-remediation-evidence.json` (superseded/historical, read in full)
- `docs/release-readiness/initial-findings.md` (grepped)
- `.scratch/release-readiness/issues/20-execute-required-relationship-production-bulk-load.md` (118 lines, read in full)
- `.scratch/company-master-pipeline/map.md` (grepped around hold notes)
- `.scratch/todos-close-out/map.md` and its four linked issue files (read/listed)
- `TODOS.md` (1,937 lines, grepped for go-live/ticket-20/blocker terms)
- `CONTEXT.md` (glossary section, lines ~100-293, read)
- `.planning/HANDOFF.json`, `.planning/STATE.md`, `.planning/active-workstream` (read)
- `.planning/workstreams/go-live/STATE.md`, `.planning/workstreams/go-live/ROADMAP.md` (tails read)
- `edgar_warehouse/scripts/build_ticket20_strict_execution_input.py` (grepped/read header)
- `edgar_warehouse/mdm/cli.py` (grepped for `--generation-id`)
- `infra/scripts/deploy-aws-application.sh` (grepped for `StrictMdmVerifyCandidate`/`StrictMdmActivate`)
- Live AWS CLI: `stepfunctions list-executions` / `describe-execution` / `list-map-runs` /
  `describe-map-run` (region `us-east-1`) against
  `edgartools-prod-bronze-seed-silver-gold` and 8 other prod state machines;
  `events list-rules` / `events list-rules --name-prefix edgartools`
- `gh pr list --state open`, `gh run list --workflow deploy.yml --limit 5`
