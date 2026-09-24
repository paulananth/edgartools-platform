# Why we care about the legacy MDM tables and the legacy mastering code

Type: research
Date: 2026-09-23
Branch: `claude/legacy-mdm-relevance-research` (at `origin/main` `3acc33e4`)
Reviewed: F2's mechanism claim was wrong and is corrected in place; see the
note at the head of that finding.
Subject: the operator's question — do legacy MDM design choices carry weight as
precedent for Clean MDM's entity-id minting, and why do we care about the legacy
tables at all?

## Verdict, first

**Two different questions hide inside one word. Separate them and the answer is
clean.**

**As design precedent for how Clean MDM mints an entity id: no weight. Both
named choices are not merely irrelevant history — they are the specific things
the accepted decisions reject, so citing either argues for something already
ruled out.**

| Choice in question | Verdict |
|---|---|
| uuid5-derived entity ids (`pipeline.py:2429`, `:3376`, `:3457`, `:3552`, `:3687`; `adv_bulk.py:287`, `:456`) | **irrelevant history — stop citing it.** ADR 0013 accepts "an internal identity ID independent of source identifiers" (`docs/adr/0013-preserve-published-mdm-identity-ids.md:3`). Every one of these seven derives the id *from* a source identifier. They are also all stub-minting paths, and one of them carries a live comment documenting the exact failure mode a derived id produces (F6). |
| a stored per-source stage table updated in place (`mdm_entity_attribute_stage`, `001_initial_schema.sql:180-191`) | **split.** Its *in-place update* (`survivorship.py:156-160`, `:280`, `:334`) is irrelevant history, contradicted by the append-only contract (`acceptance.md`'s "Runtime cannot … update/delete assertions/journal"; `024_clean_mdm_mirror.sql:28-32`; ticket 01's "a re-read adds a row instead of rewriting one"). Its *one-table-for-all-kinds shape and its name* are legitimately cited — already, in ticket 07 — but as corroboration for a conclusion three independent arguments already reach, never as the reason. |

**As a thing to care about operationally: enormously, and this is why the
question isn't just "no". Legacy is the entire running MDM.** It is what
`edgartools-prod-mdm` executes on every `load_history` and `daily_incremental`
run (F1); it owns every published entity id there is; and no automated path
installs `mdm_v2` at all — only a deliberate manual command does (F2). Clean MDM is a replacement
with a written, accepted cutover plan (`docs/specs/clean-mdm/acceptance.md`),
and that plan names legacy rows as a **migration input and a crosswalk
obligation** — not as a design input:

> Legacy rows may provide comparison/crosswalk candidates but cannot substitute
> for source evidence. (`acceptance.md`, "Snowflake Postgres qualification")

So: care about the legacy tables as *data to be migrated, compared against, and
retained through a 30-day rollback window*. Do not care about the legacy code as
*a design to learn minting from*. The one place those two could have touched —
a legacy-id → new-id crosswalk — has already been answered "no crosswalk" for
the first kind that reached the question
(`.scratch/person-consumer-contract/issues/06-decide-legacy-person-id-crosswalk.md:9`).

**The practical consequence for this map:** ticket 03's decision 3 and the
unbuilt id-minting question (03-04-challenge F2, F3) get no help from legacy.
Nothing in `clean/` mints an entity id today (F4); when that code is written, it
is being written against a blank sheet plus ADR 0013, and legacy's answers are
evidence of failure modes to avoid, not a shape to copy.

---

## What I checked

Live AWS, read-only, account `690839588395`, region `us-east-1`, on 2026-09-23:
`describe-state-machine` for `edgartools-prod-mdm`, `edgartools-prod-load-history`
and `edgartools-prod-daily-incremental`; `list-executions` for all three;
`describe-task-definition` for `edgartools-prod-mdm-medium:272`,
`edgartools-prod-mdm-small:274` and `edgartools-prod-medium:307`;
`list-state-machines`, `events list-rules`, `events list-event-buses`,
`scheduler list-schedules`.

Source: `edgar_warehouse/mdm/cli.py`'s parser and dispatch, `_handle_run`,
`_logged_handler`; `pipeline.py`'s `run_all` and the five step lambdas, its five
`uuid5` sites and their enclosing functions; `adv_bulk.py`'s two `uuid5` sites,
`resolve_advisers_bulk` and `resolve_funds_bulk`; `survivorship.py`'s
`merge_field` and `stage_candidate`; `resolvers/base.py`'s `_resolve`;
`mdm_entity_backfill.py`; `migrations/runtime.py`'s `migrate`; all
nineteen modules of `edgar_warehouse/mdm/clean/` by grep for legacy table names,
`mdm_v2`, uuid minting and uuid-version checks, and `clean/cli.py` and
`clean/store.py` line by line; `023_clean_mdm.sql`, `024_clean_mdm_mirror.sql`,
`001_initial_schema.sql`, `034_clean_mdm_stage_view_naming.sql`.

Docs: `docs/adr/0013`, `docs/specs/clean-mdm/{README,acceptance,pipeline-inventory,state-of-build}.md`,
`.scratch/company-mastering/{map.md,issues/07-per-kind-read-views.md}`,
`.scratch/clean-mdm/{map.md,local-mdm-schema-evidence.json}`,
`.scratch/person-consumer-contract/{map.md,issues/06,issues/22}`,
`.scratch/mdm-run-throughput/{map.md,issues/05}`,
`.scratch/change-propagation/issues/42`. Read
`.scratch/company-mastering/research/03-04-challenge.md` first, as instructed;
its F2/F3 findings about the unbuilt minting path are relied on and
independently re-verified here, not restated.

Parsed: `tests/fixtures/clean_mdm/v1/manifest.json` and `records.jsonl`, and the
commit that introduced them (`e2807e52`).

## What I could not check

- **Live row counts in `EDGARTOOLS_PROD_MDM`.** `MDM_DATABASE_URL` is a Secrets
  Manager secret on the MDM task definitions; reaching it means fetching a
  credential, which the brief forbids. **Live row counts are not established.**
  What *is* established from committed evidence is in F2. A prior Codex session
  reported a read-only live check finding `023`, `025` and `026` recorded; that
  is not contradicted here and is the likely trace of a manual install.
- **What produced the fixture's ten UUID-v5 ids.** Not established — see F7 for
  the search space I ruled out.
- **Whether the last `edgartools-prod-mdm` run's failure is legacy-related.** I
  read execution status and timestamps only; I did not open the failure cause or
  CloudWatch logs. Out of scope for this question.
- **Which commit built the running image.** The MDM task definitions pin
  `edgartools-prod-images@sha256:01cc00a1d8c6ae1d81450806e9ce99a58ad987c8f2f48654ad04d547254ff370`;
  I read source at `origin/main` `3acc33e4` and did not establish that the image
  was built from it. The direction of that gap is safe for every claim here: a
  staler image is *more* legacy-only, not less, since Clean MDM is the newer
  branch — and `MDM_MODEL` is absent from the task definition's environment and
  secrets whatever the image contains, so F1's routing conclusion does not
  depend on the image at all.
- **Anything about the operator's 2026-09-19 decommission directive beyond its
  two recorded citations.** It is recorded in `.scratch/` (the repo's issue
  tracker, per `docs/agents/issue-tracker.md`), not in a spec or ADR — see F8.

---

## Findings

### F1 — Legacy is the live production mastering path. Not dead code, and the only mastering there is.

`edgartools-prod-mdm` (live `describe-state-machine`, 2026-09-23) starts at
`Mastering` and runs six states:

```
Mastering → BackpropagateIdsToSilver → "Infer Relationships"
          → Publish → "Publish Relationships" → Reconcile
```

`Mastering` runs, on `edgartools-prod-mdm-medium:272`:

```
States.Array('mdm', 'mastering', '--entity-type', 'all', '--run-id', $.run_id)
```

Both live production pipelines invoke that machine as a nested synchronous
execution: `edgartools-prod-load-history`'s `RunMdmChain` and
`edgartools-prod-daily-incremental`'s `RunMdmChain`, each with
`StateMachineArn: arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-prod-mdm`.

**The legacy/clean switch, and which side production is on.** `mdm mastering`
takes `--model`, defaulting to the environment:

`edgar_warehouse/mdm/cli.py:173`:
```python
mastering.add_argument("--model", choices=("legacy", "clean"), default=os.environ.get("MDM_MODEL", "legacy"))
```

and the dispatch that reads it, `cli.py:777`:
```python
if command_name != "migrate" and getattr(args, "model", os.environ.get("MDM_MODEL", "legacy")) == "clean":
    from edgar_warehouse.mdm.clean.cli import handle
    exit_code = handle(command_name, args)
else:
    exit_code = handler(args)
```

The Step Functions command passes no `--model`. `MDM_MODEL` is absent from the
environment *and* the secrets of all three task definitions the two machines
use — `edgartools-prod-mdm-medium:272`, `edgartools-prod-mdm-small:274` (which
runs `Reconcile`, one of the commands `clean/cli.py` *does* support) and
`edgartools-prod-medium:307` — verified live. Repo-wide, `MDM_MODEL` appears in
exactly seven places, all of them `edgar_warehouse/mdm/cli.py`; `grep -rn
"MDM_MODEL" infra/` returns nothing. **Production is unambiguously on the legacy
branch.**

**The full call chain, traced:**

| Step | Site |
|---|---|
| `mdm mastering --entity-type all` | `edgartools-prod-mdm` `Mastering`, live |
| routes to the legacy handler | `cli.py:777` (model is `legacy`) |
| `_handle_run` | `cli.py:972`; `:984` builds `MDMPipeline`; `:987` calls `_run_all_with_ordinary_lease` |
| `MDMPipeline.run_all` | `pipeline.py:2898` |
| five concurrent steps | `pipeline.py:2967` companies, `:2975` advisers, `:2978` securities, `:2982` persons, `:2984` funds |
| advisers → `adv_bulk` | `pipeline.py:1081-1083` → `resolve_advisers_bulk` (`adv_bulk.py:195`), whose `uuid5` is `:287` |
| funds → `adv_bulk` | `pipeline.py:1506-1508` → `resolve_funds_bulk` (`adv_bulk.py:353`), whose `uuid5` is `:456` |

So `pipeline.py` and `adv_bulk.py` are the production mastering path, and both
`uuid5` sites the brief names in `adv_bulk.py` are live production behaviour, not
vestigial. `mdm_entity` and `mdm_entity_attribute_stage` are its output tables
(`survivorship.py:23` imports `MdmEntityAttributeStage`; `resolvers/base.py:20`
imports `stage_candidate`).

The other two commands in the chain are *not* mastering and should not be
conflated with it: `mdm publish` dispatches to `_handle_export` (`cli.py:650`),
the golden-record/mirror writer; `mdm reconcile` dispatches to
`_handle_verify_graph` (`cli.py:573`), the Snowflake graph parity check.

**One qualification on "live", for accuracy.** Wired and invoked, but not
currently scheduled or green:

- `edgartools-prod-mdm`: last `SUCCEEDED` 2026-09-06 10:37 ET; three `FAILED`
  on 2026-09-16; three `ABORTED` 2026-09-07/08.
- `edgartools-prod-load-history`: last execution 2026-08-13 (`SUCCEEDED`).
- `edgartools-prod-daily-incremental`: last schedule-shaped execution
  (EventBridge-style name) 2026-09-08 08:00 ET, `SUCCEEDED`; manual runs since,
  last one `FAILED` 2026-09-15.
- **No schedule exists now.** `aws events list-rules` on the only event bus
  (`default`) returns two Step Functions plumbing rules and nothing else;
  `list-rules --name-prefix edgartools` returns nothing; `aws scheduler
  list-schedules` returns `[]`. CLAUDE.md's `cron(0 12 ? * MON-SAT *)` for
  `edgartools-prod-daily-incremental-refresh` does not correspond to any live
  rule — consistent with the 2026-09-08 date of the last scheduled-shaped run.

None of that changes the answer: it is the production mastering path, and it is
the only one that has ever run against production data.

### F2 — No *automated* path installs `mdm_v2`. Whether it exists in the live store is not established here, and a prior live check says it does.

> **Corrected 2026-09-23 after review.** This finding originally read
> "`mdm_v2` has never been installed outside a test database" and argued that
> `mdm migrate` *structurally cannot* install it. **That is false**, and the
> error was load-bearing: `mdm migrate --model clean --application-role <role>`
> installs `mdm_v2` today (`cli.py:30-31` declares both flags; `cli.py:1649-1651`
> branches on the model and calls `clean/store.py`'s `migrate`). The exclusion at
> `cli.py:777` (`command_name != "migrate"`) does not block it — it routes
> `migrate` to `_handle_migrate`, which does the clean branch itself.
>
> What survives is narrower and still useful: **nothing in `infra/` invokes it**,
> so no deploy, Terraform root or bootstrap script installs `mdm_v2`. A human
> running the command does. That distinction matters, because a prior Codex
> session reported a read-only live check finding `023`, `025` and `026`
> recorded in `mdm_v2.migration` — which, if accurate, is exactly what a manual
> run looks like. This note could not reach the live store to settle it
> (see "Not established"), so both readings are left standing.
>
> This is also an instance of a rule this repo already wrote down: provisioning
> that is not Terraform or a committed script does not survive an account
> rebuild, however carefully a runbook describes it (`CLAUDE.md`).

**No automated code path applies 023, and therefore none applies anything after
it.**

Two migration runners exist and they do not overlap.

1. **The legacy runner**, `migrations/runtime.py:375` `migrate(engine, seed=True)`,
   applies files in an explicit list: `001`, `003`, `004`, `005`, `006`, `007`,
   `008`, `009`, `010`, `011`, `012`, then 013-018 through their privileged
   wrappers, then `019`, `020`, `021`, `022` (`runtime.py:383-408`). **It stops
   at 022.** It never mentions 023 or later — confirmed across the whole of git
   history: `git log -S "023_clean_mdm" -- edgar_warehouse/mdm/migrations/runtime.py`
   returns no commits. This is what `mdm migrate` runs.
2. **The clean runner**, `clean/store.py:57` `migrate(engine, *, application_role)`,
   installs `023_clean_mdm.sql` and then the ten files in
   `store.CLEAN_MDM_MIGRATIONS` (`store.py:43-54`: `025` … `034`).

`cli.py:777` excludes `"migrate"` from the *generic* clean dispatch
(`command_name != "migrate"`), but that is a routing detail, not a barrier:
`_handle_migrate` branches on the model itself and calls the clean runner
(`cli.py:1649-1651`). So `mdm migrate --model clean --application-role <role>`
**does** install `mdm_v2`. One narrower thing is true of `MDM_MODEL`: the
`migrate` subparser's `--model` defaults to a literal `"legacy"`
(`cli.py:30`) rather than reading the environment as the other subcommands do
(`cli.py:52`, `:173`, `:285`, `:541`, `:645`, `:675`), so exporting
`MDM_MODEL=clean` alone will not install it — only the explicit flag will.

Outside that one command, `clean/store.py`'s `migrate` has no caller beyond
`tests/integration/test_clean_mdm_postgres.py` (`:116`, `:117`, `:254`,
`:2386`, `:2714`). `grep -rn
"application_role\|023_clean_mdm\|clean.store\|mdm_v2\|MDM_MODEL" infra/` returns
nothing at all — no deploy script, no Terraform, no bootstrap. **Installing
`mdm_v2` is therefore a deliberate manual act, never something a deploy does.**
`024_clean_mdm_mirror.sql` is a third, separate target again
(`clean/publication.py:18`, "Applied only to `CHANGE_LEDGER_DATABASE_URL`",
`024:1-2`) and is not in `CLEAN_MDM_MIGRATIONS`.

**Committed corroboration.** `.scratch/clean-mdm/local-mdm-schema-evidence.json`
records `uv run edgar-warehouse mdm migrate` against a clean PostgreSQL 16:
`"table_count": 38`, every table legacy, no `mdm_v2` schema, and
`"scope": "Current runtime MDM schema applied to local PostgreSQL 16; not Clean
MDM shared-identity implementation"`.

**Legacy volumes, from committed run records (live counts not established).**

| Table | Rows | Source |
|---|---|---|
| `mdm_entity_attribute_stage` (prod) | 2,577,622 → 1,732,055 after the 2026-09-11 backfill | `.scratch/mdm-run-throughput/map.md:37` and `issues/05-...md:190` |
| `mdm_entity` where `entity_type='fund'` (prod) | 130,615 | `.scratch/change-propagation/issues/42-fund-dedup-keyed-on-pfid-starves-mdm-export.md:88` |
| stage rows for fund entities (prod) | 653,075 | same, `:92` |
| every `mdm_v2` table | no automated installer; live presence not established — see F2 | — |

The asymmetry is the answer to "why do we care": millions of rows on one side
that every current consumer reads, and a schema that exists only in integration
tests on the other.

### F3 — Clean MDM is a replacement, and the migration/retirement plan is written down. Here is exactly what it commits to.

`023_clean_mdm.sql:1-2` states the relationship in its own header:

```sql
-- Clean MDM v1. Explicit opt-in migration; the legacy MDM remains untouched.
```

`docs/specs/clean-mdm/README.md:3` — "Q1–Q16 accepted; local shared-core
implementation in progress. No hosted qualification or consumer cutover has
occurred." And `:54-56`:

> The old separate-domain identity model remains a description of the running
> system. This effort is the explicitly requested migration to shared identities;
> it does not retroactively mark the old model as an error.

That last sentence is the most precise statement of the answer to the operator's
question, and it cuts both ways: legacy is not an error to be repudiated, and it
is not an authority to be deferred to. It is the description of what runs.

**The written plan is `docs/specs/clean-mdm/acceptance.md`,** and it commits to
these things specifically (quoting its own words):

- **A gated sequence, not a date.** Local PostgreSQL 16 acceptance (a 16-row
  gate matrix) → Snowflake Postgres qualification → "Catch-up, cutover and
  rollback rehearsal" steps 1-6. The operator deferred the middle step: "The
  user selected local PostgreSQL for continued qualification on 2026-09-19;
  Snowflake qualification is deferred."
- **Legacy stays readable, and is not auto-deleted.** "The accepted rollback
  retention period is 30 days after cutover. … Retain old MDM through that
  window; this is not an automatic deletion schedule." And "Keep old MDM
  read-only for audit and in a demonstrably recoverable state for the agreed
  rollback window."
- **Consumers are not moved implicitly.** "Old consumers remain on the retained
  old MDM unless an explicit read-only compatibility projection is proven."
- **Legacy rows are a comparison input, never a substitute for source
  evidence.** "Rebuild new MDM from those inputs. Legacy rows may provide
  comparison/crosswalk candidates but cannot substitute for source evidence."
  And "Never manufacture synthetic duplicate identities just to make a legacy
  row count match."
- **A crosswalk is required in principle.** "Publish old-ID → new-ID/profile
  mappings with ambiguous cases unresolved." **This is the only clause in the
  whole corpus that would make legacy ids matter to `mdm_v2`** — and see F4/F8
  for how the first kind to reach it actually answered.
- **Five things still open before a switch.** "settle the exact target identity,
  consumer routing mechanism, acceptable pause/lag, legacy catch-up method and
  rollback triggers."

**`docs/specs/clean-mdm/pipeline-inventory.md` is the per-path migration map** —
a 17-row table of "Current identity / role / relationship effects" against
"Target routing and publication", covering Company, ADV Adviser, ADV Fund,
Person, Security, 13F, proxy, audit, hierarchy, relationships, stewardship,
export, graph and API. It is the artifact that makes "migration plan" concrete
rather than aspirational, and it already adjudicates the stage table (see F5).

**And there is a decommission directive.** Recorded twice in the issue tracker:
`.scratch/person-consumer-contract/map.md:47-49` — legacy MDM "is being
decommissioned (operator directive, 2026-09-19) and is cited here only as
evidence of current behavior" — and
`.scratch/person-consumer-contract/issues/06-...md:19`. The inventory of what
that means for one kind is `issues/22-decommission-legacy-person-code-and-tests.md`
(status open), gated: "Do not start before the Clean MDM Person consumer is
live: until then these paths are the only Person production there is, however
flawed."

### F4 — The two id spaces are disjoint in both directions. Nothing carries a legacy id into `mdm_v2`, and nothing requires them to agree.

Precisely: **disjoint in identity minting, and disjoint as evidence content.**
Legacy ids do flow outward, to Snowflake silver — but never into `mdm_v2`, and
no Clean MDM adapter's declared field list reads them back. Six checks, all
negative:

1. **No legacy table is named anywhere in `clean/`.** `grep -rn
   "mdm_entity\|mdm_company\|mdm_adviser\|mdm_person\|mdm_security\|mdm_fund\b\|attribute_stage\|MdmEntity"
   edgar_warehouse/mdm/clean/` → zero hits across all nineteen modules.
2. **No `mdm_v2` reference exists anywhere in `edgar_warehouse/` outside
   `clean/`.** `grep -rn "mdm_v2" --include=*.py edgar_warehouse/ | grep -v
   "/clean/"` → zero hits. Repo-wide, `mdm_v2` appears only in `clean/`, in
   `tests/integration/test_clean_*`, and in docs/`.scratch` prose.
3. **`clean/` mints no entity id at all.** The only uuid generation in the whole
   package is `bookkeeping.py:7,29` — `uuid4()` for a run *attempt* id, not an
   entity. `mdm_v2.identity.entity_id` has no `DEFAULT`
   (`023_clean_mdm.sql:53-58`), and ids arrive pre-minted in the pinned manifest
   (`clean/cli.py:291` `batch.get("identities", [])` — `03-04-challenge.md` F3
   cites `:290`, which is the neighbouring `"assertions"` key), validated only for
   uniqueness and parseability: `merge.py:354-356` raises on a duplicate, then
   calls a bare `UUID(i["entity_id"])`. This independently confirms
   03-04-challenge F2's closing observation.
4. **No uuid *version* is checked anywhere.** `grep -rn "\.version\b\|uuid5"
   edgar_warehouse/mdm/clean/` → nothing; `023:54` is `entity_id uuid PRIMARY
   KEY` with no constraint. A v1, v4, v5 or v7 id is equally acceptable to the
   store today.
5. **The one module whose job is propagating legacy ids points the other way.**
   `edgar_warehouse/mdm_entity_backfill.py` is `backfill-mdm-entity-ids`, the
   `BackpropagateIdsToSilver` state in F1's chain. Its own docstring (`:1-27`)
   is unambiguous about direction: it reads silver rows with
   `mdm_entity_id IS NULL` from `EDGARTOOLS_SILVER`, looks the id up in **legacy
   MDM Postgres** (`MdmSourceRef`, "populated by the existing resolvers via
   `BaseResolver._register_source`"), and re-emits the full row to silver. Its
   six `_TableSpec` targets (`:105-145`) are all legacy `entity_type`s —
   `company`, `person`, `security`, `adviser`. It never reads or writes
   `mdm_v2`. So legacy → silver, and it stops there.
6. **No legacy id is readable as evidence content either.** `grep -rn
   "mdm_entity_id" edgar_warehouse/mdm/clean/` → zero hits, so a legacy id
   cannot reach `mdm_v2.assertion.body` through an adapter. Confirmed
   positively at the declared field lists rather than by absence:
   `company_source.FIELDS` (`company_source.py:24-31`) is six SEC submissions
   fields — `entity_name`, `sic`, `sic_description`, `state_of_incorporation`,
   `fiscal_year_end`, `description` — and its `identifiers` map is
   `{"cik": "cik"}` (`:50`); GLEIF's mapping is built at `gleif_source.py:378`.
   None names `mdm_entity_id`. This also verifies at the file what
   `.scratch/person-consumer-contract/issues/22` asserts in prose — that
   silver's `mdm_entity_id` columns are "frozen as legacy: never read, never
   rewritten by Clean MDM."

The only clause that would ever require agreement is `acceptance.md`'s "Publish
old-ID → new-ID/profile mappings". **And the first kind to actually reach that
question answered it in the negative.**
`.scratch/person-consumer-contract/issues/06-decide-legacy-person-id-crosswalk.md:9`:

> **No crosswalk. Legacy Person IDs are dropped, not mapped.**

Its reasoning is worth carrying to Company, because it is a method rather than a
Person fact — it enumerates the holders and finds none that needs them
(`:15-24`): legacy Postgres is being decommissioned; silver's `mdm_entity_id`
and the graph's person nodes live in a Snowflake that will not be restored; the
API is undeployed; and **gold never used them** (owners key on a hash of
`'cik:'||owner_cik` else `'name:'||owner_name_norm`,
`ownership_holdings.sql:63-67`). It also rejects them on their merits (`:32-39`):
legacy's fuzzy context check can never pass, so `REVIEW` bound anything scoring
≥ 0.80 Jaro-Winkler with no human gate — "Carrying those ids forward would
import silent over-merges into a contract whose point is measured precision."
**Re-verified at the file rather than taken on trust**, since it carries weight
here: `resolvers/base.py:268-288` creates a new entity only when
`verdict is None or verdict.action == MatchAction.QUARANTINE` (`:268`); every
other verdict, `REVIEW` included, falls through to `:283-288` and returns
`verdict.candidate_entity_id` — it binds.
What does carry is **human judgment re-entered as evidence**: resolved
`mdm_match_review` rows and merge tombstones harvested as source assertions to be
re-adjudicated (`:41-48`).

### F5 — The stage table's *shape* is cited and survives; its *in-place update* is exactly what the new contract forbids. Do not let the ticket-07 citation license the second.

**What legacy does.** `mdm_entity_attribute_stage` (`001_initial_schema.sql:180-191`)
is mutated in three places on the live path:

- `survivorship.py:156-160` — `UPDATE ... SET was_selected = True` on the winning
  row, i.e. the merge outcome is written back onto the evidence row.
- `survivorship.py:276-281` — an existing stage row's `field_value`,
  `global_priority`, `effective_date`, `loaded_at` and `was_selected` are
  overwritten in place.
- `survivorship.py:331-335` — the cached representative row is likewise rewritten.

**What Clean MDM accepts instead.** Append-only, in four places:

- `acceptance.md`, permission-enforcement gate: "Runtime cannot DDL, truncate,
  alter activated policies, or **update/delete assertions/journal**".
- `024_clean_mdm_mirror.sql:28-32` — an `immutable_row()` trigger raising "MDM
  commit mirror is append-only" on any `UPDATE` or `DELETE`.
- Company mastering ticket 01, as recorded at `map.md:60-69`: "**a re-read adds a
  row instead of rewriting one**" and "**assertions are never pruned**, since the
  store is append-only throughout".
- And `pipeline-inventory.md` has already adjudicated the legacy design
  explicitly, in its "Reusable foundations and gaps" section:

  > `mdm/survivorship.py:132`, `:172`, `:353` stages candidates and winners.
  > Null/empty filtering and load-time tie-breaking do not satisfy the new
  > correction, deletion and order-independent policy contract.

**Where the legitimate citation is, and why it is narrow.**
`.scratch/company-mastering/issues/07-per-kind-read-views.md:23` cites the legacy
table under "What exists" — "The legacy `mdm_entity_attribute_stage` was likewise
one table for all kinds, keyed `(entity_id, source_system, source_id,
field_name)`" — and `:87` cites it again for the *name*: "it is what the legacy
design called the same shelf … and what the wider practice calls a staging
table." Both are fine, and neither is load-bearing: the decision at `:31-38`
rests on three independent arguments (one filing touches two kinds in one
transaction; the shapes are identical because the claim is jsonb; a ninth kind
costs one word not a table), with legacy appearing as corroboration. Migration
034's own header (`:1-7`) does the same for the rename.

So the precedent is doing one honest job — supplying vocabulary for a shelf whose
shape was decided on its own merits — and must not be extended to the one thing
that makes the legacy table what it is, which is that the merge writes back onto
it.

### F6 — The uuid5 sites are all stub-minting, and one of them documents the failure mode in its own comment.

The seven sites, with their enclosing functions and keys:

| Site | Function | Key |
|---|---|---|
| `pipeline.py:2429` | `_ensure_disclosed_subsidiary` (`:2419`) | `sec:subsidiary:{source_key}` |
| `pipeline.py:3376` | `_ensure_thirteenf_manager` (`:3367`) | `sec:13f-manager:{normalized_cik}` |
| `pipeline.py:3457` | `_audit_firm_entity_id` (`:3426`) | `pcaob:firm:{normalized_id}` |
| `pipeline.py:3552` | `_ensure_proxy_person` (`:3520`) | `{company_cik}:{normalized}`, NAMESPACE_DNS, `resolution_method="uuid5_proxy_stub"` |
| `pipeline.py:3687` | `_ensure_security_by_cusip` (`:3598`) | `cusip:{cusip}`, NAMESPACE_DNS |
| `adv_bulk.py:287` | `resolve_advisers_bulk` (`:195`) | `identity(row)` — the CRD/accession identity |
| `adv_bulk.py:456` | `resolve_funds_bulk` (`:353`) | `identity(row)` — PFID or accession/index |

Every one is a fallback: *nothing matched, so mint deterministically from the
source key*. That is a reasonable engineering answer to "avoid duplicate-key
crashes on reprocessing", and it is a different question from the one Clean MDM
is asking. ADR 0013's accepted answer — "keep an internal identity ID independent
of source identifiers and role changes" — rules it out on purpose: a uuid5 over
`cusip:` or `sec:13f-manager:{cik}` is *definitionally* the id being a function
of a source identifier, so a re-identified CUSIP or a CIK change moves the id.

The live cost is documented in the codebase itself, at `adv_bulk.py:446-455`:

```python
# Check the row's own deterministic entity_id first. A fund without
# a private_fund_id dedups on (adviser_entity_id, name), but
# adviser_entity_id can flip from None to a real id on a later run
# once that adviser becomes resolvable -- the stored fund is then
# keyed under the old (None, name) pair and this lookup misses it,
# even though identity(row) (and so entity_id) is unchanged. Without
# this check the code below re-attempts an insert under the same
# primary key and crashes with a duplicate-key IntegrityError.
```

That is the derived-id failure mode stated in full by the code that has it:
identity derived from mutable context, a lookup that misses, a primary-key
collision, and a defensive pre-check bolted on to survive it. It is useful
evidence of what to avoid. It is not a design to inherit.

Note also that legacy's *non*-stub path does not use uuid5 at all: `mdm_entity`
mints from `gen_random_uuid()` (`001_initial_schema.sql:26`), and
`universe.py:76` uses `uuid4()`. So "legacy mints uuid5 ids" was never even the
legacy rule — it was the legacy *fallback* rule, in seven named places.

### F7 — The fixture's ten UUID-v5 ids are normatively inert, and their generator is not in the repo.

Confirmed by parsing `tests/fixtures/clean_mdm/v1/manifest.json`: all ten
`identities[].entity_id` values are UUID **version 5** (`b144d8f4-6456-**5**801-…`
and nine more).

**Whatever produced them is test-only, because there is no production consumer of
any generator:** `clean/` mints nothing (F4), nothing checks the version (F4),
and the fixture is loaded only by `tests/integration/test_clean_mdm_postgres.py:974`
and `:2765`.

**What produced them is not established.** `git log --diff-filter=A` puts the
whole fixture in one commit, `e2807e52` ("Build Clean MDM PostgreSQL core and
bounded Company integration", #657), whose file list contains the five fixture
files as data and no generator script. I tried to reproduce the values and
could not, over: four standard namespaces (DNS, URL, OID, X500) × nine name
templates (`{key}`, `fixture.representative:{key}`, `mdm_v2:{key}`,
`company:{key}`, `clean:{key}`, `fixture:{key}`, `synthetic:{key}`,
`representative-v1:{key}`, `fixture.representative/{key}`) × the ten record keys;
the same namespaces over each record's `subject_key`
(`digest(["fixture.representative", key])`, per `evidence.py:33-35`), each
decision's `evidence[0]` assertion id and each `decision_id`; and a
truncate-sha256-and-set-version-bits construction over all three. Zero matches.
Most likely hand-authored or produced by an uncommitted script. **The honest
statement is that their v5-ness proves nothing about minting policy, and that is
true regardless of what produced them.**

### F8 — Two places where the record is thinner than the conclusion resting on it.

Worth flagging so the next session does not over-read either.

- **The decommission directive lives only in `.scratch`.** "Legacy MDM … is being
  decommissioned (operator directive, 2026-09-19)" appears at
  `.scratch/person-consumer-contract/map.md:49` and, restated, at
  `issues/06-...md:12-13, :19`. That is the repo's issue tracker and therefore a
  primary decision record (`docs/agents/issue-tracker.md`) — but it is *not* in
  `docs/specs/clean-mdm/` or an ADR, and `acceptance.md`, which is the accepted
  cutover contract, says the opposite-sounding thing in its own voice ("Retain
  old MDM …; this is not an automatic deletion schedule"). These reconcile
  (decommission the *path*, retain the *store* through rollback), but a reader
  who finds only one of them will get a different impression.
- **"No crosswalk" is decided for Person, not for Company.** Ticket 06's holder
  table is Person-specific, and its strongest leg — "gold never used them" — is a
  claim about `ownership_holdings.sql:63-67`, a person-keying detail. Company's
  gold surface includes `mdm_company`, which is a different fact pattern I did
  not audit. The *method* transfers; the conclusion has not been re-derived for
  Company, and `acceptance.md`'s crosswalk clause is still live for it.

---

## Citation audit

Every `path:line` the brief names, checked on `origin/main` `3acc33e4`.

| Cited as | Points to | Match? |
|---|---|---|
| `pipeline.py:2429` | `uuid5(NAMESPACE_URL, f"sec:subsidiary:{source_key}")` in `_ensure_disclosed_subsidiary` | **yes** |
| `pipeline.py:3376` | `uuid5(NAMESPACE_URL, f"sec:13f-manager:{normalized_cik}")` in `_ensure_thirteenf_manager` | **yes** |
| `pipeline.py:3457` | `uuid5(NAMESPACE_URL, f"pcaob:firm:{normalized_id}")` in `_audit_firm_entity_id` | **yes** |
| `pipeline.py:3552` | `uuid5(NAMESPACE_DNS, f"{company_cik}:{normalized}")` in `_ensure_proxy_person` | **yes** — note NAMESPACE_**DNS** here, not URL, unlike the first three |
| `adv_bulk.py:287` | `uuid5(NAMESPACE_URL, identity(row))` in `resolve_advisers_bulk` | **yes** |
| `adv_bulk.py:456` | `uuid5(NAMESPACE_URL, identity(row))` in `resolve_funds_bulk` | **yes** |
| `001_initial_schema.sql:180-191` | `CREATE TABLE mdm_entity_attribute_stage` — opens at 180, closes at 191 | **yes** — exact |
| "`mdm_v2.identity.entity_id` is a uuid" | `023_clean_mdm.sql:54`, `entity_id uuid PRIMARY KEY`, no default, no version constraint | **yes** |
| "`tests/fixtures/clean_mdm/v1/manifest.json`'s ten entity ids are all UUID version 5" | ten `identities` entries in one batch, all parse to `version == 5` | **yes** — independently parsed |
| "migrations 027-034 believed unapplied; live store sits at 026" | 023-034 are applied by a *different* runner with no production caller | **no** — see F2. The premise understates the gap: `mdm_v2` is not installed at all outside integration tests |
| `pipeline.py:3687` (not in the brief's list, found here) | `uuid5(NAMESPACE_DNS, f"cusip:{cusip}")` in `_ensure_security_by_cusip` | a **seventh** site the brief's six omit |

Two pointers from the existing notes, re-checked because this question leans on
them:

| Cited at | Points to | Match? |
|---|---|---|
| `03-04-challenge.md` F3, "no `uuid4()` exists anywhere in `clean/`" | true for entity ids; `bookkeeping.py:29` has a `uuid4()` for a run **attempt** id | **near** — the claim holds for identity minting, which is what it was making |
| `03-04-challenge.md` F3/F4, `cli.py:290` for `batch.get("identities", [])` | `clean/cli.py:291`; `:290` is the `"assertions"` key one line above | **off by one** |
| `map.md:33`, `store.py:162` for the automatic-rule refusal | the refusal is `clean/store.py:169-170` | **no** — already recorded as stale in `03-04-challenge.md` F9; unchanged |

---

## What the operator should check by hand

1. **Whether the Company crosswalk question is actually open** (F8). Person
   answered "no crosswalk" by enumerating holders; Company has a gold consumer
   Person does not (`mdm_company`). Either re-derive the holder table for
   Company or record that `acceptance.md`'s crosswalk clause is superseded for
   every kind, not just Person. This is the only route by which a legacy id
   could ever have to reach `mdm_v2`, so settling it closes the question for
   good.
2. **Whether the 2026-09-19 decommission directive should be promoted out of
   `.scratch`** (F8) — into `docs/specs/clean-mdm/state-of-build.md` or an ADR,
   beside `acceptance.md`'s retention language, so the two are read together.
3. **Whether `mdm_v2` is expected to exist in `EDGARTOOLS_PROD_MDM` at all**
   (F2). Nothing installs it; if someone believes it is there, that belief needs
   a live check the operator can run with credentials in their own terminal. If
   it is *not* meant to be there yet, the "027-034 unapplied" framing should be
   corrected wherever it is written down, because it implies 023-026 are.
4. **Whether ticket 03's minting decision should record ADR 0013 explicitly**
   (F6, and 03-04-challenge F3's closing paragraph). The moment decision 3 is
   built it needs a minting rule, ADR 0013 already constrains it ("independent
   of source identifiers"), and the seven legacy sites are the worked example of
   the constraint being violated — which is a reason to *cite them as a
   counterexample*, not to leave them uncited and risk someone reaching for them
   as a pattern.
5. **Nothing here needs `pipeline.py` or `adv_bulk.py` changed.** They are
   production. The finding is about what they may be cited *for*, not about their
   correctness — with the single exception of `adv_bulk.py:446-455`, which is
   already fixed and merely documents the cost.
