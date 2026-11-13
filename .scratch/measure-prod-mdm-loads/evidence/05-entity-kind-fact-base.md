# Evidence — entity-kind fact base for the contribution/completion model

Date checked: 2026-11-13. Read-only inspection; no production connection, no writes.

This file holds the **facts** the entity-model ticket decides over. The decision itself is the
ticket's answer.

## 1. The two authorities for the source/dataset-to-kind map

`rules entity-types` (the plan's named authority) returns **14 contracts**:

| Kind | Contracts | How the kind is decided |
|---|---|---|
| `company` (7) | `gleif.level1.v1`, `gleif.relationships.v1`, `gleif.reporting_exceptions.v1`, `iapd.adv.custodians.v1`, `iapd.adv.filings.v2`, `sec.company.v1`, `sec.nport.registrant.v2` | 1 source-field, 2 rule, 4 fixed |
| `security` (4) | `openfigi.security.v4`, `sec.nport.security.v2`, `sec.ownership.security.v2`, `sec.thirteenf.securities.v2` | all fixed |
| `person` (2) | `sec.ownership.reporting_owner.v1`, `sec.submissions.person.v1` | both rule |
| `fund_structure` (1) | `sec.nport.fund.v1` | fixed |

`rules/merge/kinds/*.yaml` `defaults.sources` lists **13**. The one difference is
`gleif.reporting_exceptions.v1`: its contract states `company`, but the company kind does not list
it, because it maps no field and no rule. Every merge-kind rule source appears in its kind's list,
and every list member has a rule.

## 2. Declared link/derive steps per kind

| Kind | Target | Link step | Derives | Retained intervals | Run state |
|---|---|---|---|---|---|
| `company` | `gleif/mastering` | `links` | `relationship` from `mastering_record` (`rules/sources/gleif/source.yaml:67-70`) | **0** | 7 runs, 0 complete, 7 running |
| `person` | — | **none declared** | — | — | `sec.submissions.person/mastering` 149 complete; `sec.ownership/mastering` 8 of 9 |
| `security` | `sec.nport.security/mastering` | `links` | `relationship` from `mastering_record` (`rules/sources/sec.nport.security/source.yaml:890-897`) | **0** | 6 runs, 0 complete, 6 running |
| `security` | `sec.nport.security/mastering_other_keys` | none | — | no retained run rows | 4 bundles in the later manifest wave only |
| `fund_structure` | `sec.nport.fund/mastering` | `links` | `relationship` from `mastering_record` (`rules/sources/sec.nport.fund/source.yaml:40-43`) | **1** (state complete) | 1 run, complete |

`sec.company-facts/silver` also declares `line_items` and `measures` derives, but that target is
silver-only and feeds no MDM kind; its retained run is `running`.

## 3. The skill's completion criterion

`skills/data-operations/SKILL.md:216-228`:

- "A golden record of an entity type comes from every source whose records name one, not from a
  single source. So one source's load is that source's part of the entity, never the entity."
- "'The entity is loaded' is true only when every source of the kind has loaded."
- "**The entity is done when** each source of its kind has loaded, the links between them have run
  (identifier joins as records arrive; name pairing through its pass where the rules declare one),
  and **the explained count finds no record unexplained, counted for every source at once**."
- "Do not size the entity by its first source."

## 4. The explained count — what it is, and whether retained evidence carries it

**Definition** (`edgar_warehouse/mastering/reads.py:61-66`): a stored source record bound to a
golden record is *explained* when it was explained by a `bind` decision, when it is the one record of
that golden record that created it (unless a decision says otherwise), or when it shares an
identifier with another record in that golden record. A bound record fitting none of those is
**unexplained**. `reads.py:68-115` computes it across stored records with a golden-record
association, grouped by golden record, and returns totals plus nonzero per-source unexplained
counts. `reads.py:135-136` nests it under `explained` in the broader store-counts response.

**It is not a deferred/set-aside count.** Deferred records have not entered this bound-record
accounting at all.

**Nothing in the retained evidence carries it.** The read-side check
(`mastering.reads.explained` / the store counts response) is the only producer of
`records_bound`, `by_decision`, `created`, `by_identifier`, `unexplained` and
`unexplained_by_source`. The `mastering.merge` worker returns a receipt with `version` and
`files` (`file`, `records`) and no explained count (`edgar_warehouse/workers/mastering_merge.py:77-109`);
the merge result itself carries `file`, `skipped`, `records`, `released` and operation-specific
counters (`edgar_warehouse/mastering/merge.py:126-133, 219-243`). The per-source quality report
carries `records`, `set_aside`, `empty_rate`, `newest`, `newest_age_days`
(`edgar_warehouse/mdm/quality.py:407-438`).

Retained exports, field by field:

| Export | Fields present | Explained count? |
|---|---|---|
| `measure-prod-source-outcomes.json` | per contract: `records`, `deferred`, `blocking_deferred`, `open_reviews` | **No** |
| `measure-prod-step-intervals.json` | per run/step: `run_id`, `source`, `target`, `state`, `units`, `verified`, `pending`, `run_created`, `run_completed`, `step`, `step_first`, `step_last`, `events` | **No** |
| `measure-prod-target-summary.json` | per target: run counts, states, rule versions, captures, worklist hashes, step intervals, load summaries, manifest invocations | **No** |
| `measure-prod-runs.json` / `-runs-verified.json` | per run: state, units, verified, pending, created, completed, checks, summary | **No** |
| `measure-prod-fast-20261112-141251-ET/report.json` | the whole 2026-11-12 report | **No** |

**Consequence:** from retained evidence alone the report **cannot** assert that the explained count
is zero, and therefore **cannot** assert that a kind satisfies the skill's full "entity is done"
criterion. That assertion needs a fresh read-side check against the store — which the closed
credential gate forbids.

## 5. What the 2026-11-12 snapshot asserted, for comparison

Its entity rows used `status`, `first_verified_contribution_at_et`,
`all_required_target_completion_at_et`, `blocking_deferred`, `unique_master_count` and a
`required_target_statuses` map. It reported:

| Kind | Status | First verified contribution (ET) | Required target statuses | blocking_deferred |
|---|---|---|---|---|
| `company` | partial | 2026-11-10 22:04:11 | gleif/mastering partial, iapd.adv/custodians partial, iapd.adv/mastering complete, sec.company/mastering complete, sec.nport.registrant/mastering complete | 71,139 |
| `person` | partial | 2026-11-11 23:22:36 | sec.ownership/mastering partial, sec.submissions.person/mastering complete | 0 |
| `security` | blocked | 2026-11-10 22:26:58 | openfigi/mastering partial, sec.nport.security/mastering partial, sec.ownership/security_symbols blocked, sec.thirteenf.securities/mastering complete, gleif/subfund-pairs complete | 0 |
| `fund_structure` | partial | 2026-11-11 00:33:20 | sec.nport.fund/mastering complete | 7 |

Note `fund_structure`: its only target is complete and its all-source completion timestamp is set,
yet its status is `partial` — because 7 records are `blocking_deferred`. That snapshot therefore
folded deferred counts into the status, and listed `gleif/subfund-pairs` (a link target, not a
contract) among the security kind's required targets.

## 6. A rule-version hazard the report must handle

The retained runs were frozen under two rule versions: `rules-2026-11-11.go-live-hosted-2` (370
runs) and `rules-2026-11-10.go-live-8` (21 runs). The current checkout's target shapes changed
afterwards — commits `8cf2afda` (2026-11-12 22:17 ET), `247b9e3a` and `86dc6faf` (2026-11-12
23:38 ET) reshaped the extract passes. Comparing the retained step names against the current
Rules:

| Target | Steps in the current Rules with no retained interval | Retained step names no longer in the current Rules |
|---|---|---|
| `gleif/mastering` | `links`, `processed` | — |
| `iapd.adv/custodians` | `read_custody` | `read` |
| `sec.company/mastering` | `main`, `catalog`, `combine` | — |
| `sec.nport.registrant/mastering` | `registrants` | `filings` |
| `sec.nport.security/mastering` | `filings`, `links`, `processed` | — |
| `sec.company-facts/silver` | `line_items`, `measures`, `processed` | — |
| `sec.nport.security/mastering_other_keys` | whole target — no retained intervals | — |
| `sec.ownership/security_symbols` | whole target — no retained intervals | — |
| `sec.company/capture`, `sec.registration/capture` | capture targets — no retained intervals | — |

**The retained evidence predates the current Rules.** A step name in the report must carry the
rule version that produced it, and a step the current Rules declare but the retained runs did not
run (notably `gleif/mastering`'s `links` and `sec.nport.security/mastering`'s `links`) must be
reported as *not evidenced*, never as *completed*.
