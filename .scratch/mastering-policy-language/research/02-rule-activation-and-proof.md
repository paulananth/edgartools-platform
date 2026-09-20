# Research: how a declared rule becomes active, and where its proof lives

Ticket: [02](../issues/02-research-rule-activation-and-proof.md). Map:
[Mastering Policy Language](../map.md). Date: 2026-09-20. Read against the
`claude/mastering-policy-language` worktree (Clean MDM files read-only; `path:line`
citations are into that tree). Builds on
[research 01](01-policy-document-granularity.md) — the digest pin and the
cross-kind closure are established there and not re-derived here. Vendor claims
cite the vendor's own documentation page; nothing below rests on a blog post.

## 1. The simple solution

**Write the rule once, in its kind's document. Activate it with a separate
one-line entry that names the rule by id and version, names the one verdict it
is allowed to decide automatically, and carries the measurement that earned it:
how many decisions were checked, how many were right, the resulting lower bound,
who approved it and when, and the SHA-256 of the sample files anyone can re-score.**
The bar the rule must clear is declared once per identity kind — 99.9% for
Company, 99% for Person — in that kind's own document, so the operator's own
"99% for Person only" decision is one line in one place. A rule with no
activation entry still fires; its result just goes to a Steward instead of
binding. Because the rule, the bar and the proof all live in the same policy body,
and a batch pins that body by one hash, they can never drift apart: edit the rule
and its version no longer matches the activation entry, so the document is
refused at registration; raise the bar and, when that new document is registered,
every rule whose lower bound now falls short is refused by the same arithmetic —
nobody has to hunt down which rules the change invalidated; replay an old
batch and it reproduces exactly the decision the policy of that day authorised,
because the pinned body is immutable. The proof stays small — about 900 bytes per
activated verdict, numbers and hashes only. The 15 MB of labelled samples behind
research 18 stay outside as files, named by hash. **No new table, no new status
column, no new activation switch** — Clean MDM already makes policy registration
owner-only and forbids the runtime from changing policy activation, so
"who approves" is answered by the privilege boundary that exists today.

## 2. The recommended shape

**Option (a), with the hash pointer of (c) — and the outside artifact is a
*file*, not a table row.** The numbers live next to the rule; the sample is
referenced by SHA-256. Option (b) is rejected: it needs its own table, its own
status machine and its own uniqueness guarantee, all of which the digest already
provides for free, and Clean MDM explicitly warns against building "a competing
activation registry" (`docs/specs/clean-mdm/recovery.md:51`).

Three ideas carry the whole design.

**(i) The unit of activation is `(rule_id, rule_version, verdict)`, not the rule.**
Research 18 measured rule C-J's two arms separately and they landed in different
places: the `person` arm 841/841 (LCB 0.9955) and the `entity` arm 507/507 only
under a guard written after both errors were seen
(`.scratch/person-consumer-contract/research/18-reporting-owner-classification-precision.md:234`,
`:341-346`). Person ticket 03's release gates say exactly this — gate 1 lets
automatic `person` go live, gate 2 holds automatic `entity` back for
re-measurement (`.scratch/person-consumer-contract/issues/03-decide-reporting-owner-classification.md:92-97`).
Per-verdict activation expresses that with no extra machinery: list the `person`
arm, omit the `entity` arm, and the same rule runs automatically for one verdict
and review-only for the other.

**(ii) Activation is a pointer, not an edit.** The operator never edits a rule to
turn it on. Because the entry names `rule_version`, any change to the rule body
(which bumps its version) orphans the entry and the document is refused — the
rule silently falls back to review-only rather than inheriting a proof measured
on its predecessor.

**(iii) The check is arithmetic, so a bar change needs no bookkeeping.** The
Merge Stage recomputes the lower bound from `n` and `correct` and compares it to
the kind's declared bar. Changing a bar means editing the body, which mints a new
digest — the *old* digest and every batch pinned to it are untouched, as they must
be. What the arithmetic buys is that nobody has to work out *which* rules the
change invalidated: lowering Person's bar from 99.9% to 99% leaves a rule that
already cleared 99.9% qualified, and raising it makes the new document fail
registration until every entry that now falls short is removed or re-proved. The
operator meets that at authoring time, not in production.

One field-shape caveat for Codex: the example nests `fields` under
`kinds[kind]`, but `select_fields` reads `policy["fields"][kind]`
(`edgar_warehouse/mdm/clean/survivorship.py:200`). Either keep `fields` at the
top level or move that read — research 01 §2 already flags the same choice; it is
orthogonal to activation.

### The body

```json
{
  "version": "edgartools-policy-v3",
  "required_consumers": ["journal", "export", "graph"],

  "kinds": {
    "person": {
      "version": "person-v2",
      "bars": {
        "classification": { "min_precision": 0.99, "method": "wilson_lower_bound", "one_sided_confidence": 0.975 },
        "binding":        { "min_precision": 0.99, "method": "wilson_lower_bound", "one_sided_confidence": 0.975 }
      },
      "classification": { "rules": { "C-J": { "version": "2026-09-20", "emits": ["person", "company", "entity_undetermined", "deferred"], "steps": ["..."] } } },
      "binding":        { "rules": { "tier-b-context-key": { "version": "2026-09-20", "emits": ["bind"], "steps": ["..."] } } },
      "fields":         { "...": "per-field survivorship, research 01 §2" }
    },
    "company": {
      "version": "company-v4",
      "bars": { "binding": { "min_precision": 0.999, "method": "wilson_lower_bound", "one_sided_confidence": 0.975 } },
      "binding": { "rules": { "tier-a-cik": { "version": "2026-08-01", "emits": ["bind"], "steps": ["..."] } } },
      "fields":  { "...": "..." }
    }
  },

  "automatic_rules": [
    {
      "kind": "person",
      "family": "classification",
      "rule_id": "C-J",
      "rule_version": "2026-09-20",
      "verdict": "person",
      "proof": {
        "method": "wilson_lower_bound",
        "one_sided_confidence": 0.975,
        "n": 841,
        "correct": 841,
        "lower_bound": 0.99545,
        "recall": null,
        "deferral_rate": 0.011,
        "adversarial": { "fixture_sha256": "0f2c…", "violations": 0 },
        "cohort": {
          "description": "Form 3/4/5 reporting owners from bronze filing_artifact; labelled once per distinct owner CIK",
          "source_codes": ["sec.ownership.reporting_owner.v1"],
          "drawn_at": "2026-09-20T00:00:00+00:00",
          "seed": "20260920",
          "n_population": 4831,
          "files": {
            "18-sample.jsonl":  "87209b16a555c57e02ec3a47ee093a84eaa2527e09c55b4eeecc1d39f3dad423",
            "18-owners.jsonl":  "8181e1bf6e17b1476d9e080a96c69e2093fb708849c391e0961703abda19ff1c",
            "18-classify.py":   "<sha256>"
          }
        },
        "approved_by": "operator:paul",
        "approved_at": "2026-09-20T12:00:00+00:00",
        "reason": "research 18, rule C-J person arm: 841/841, Wilson LCB 0.9955 >= 0.99"
      }
    }
  ]
}
```

The two `sha256` values above are the real ones research 18 recorded
(`.scratch/person-consumer-contract/research/18-summary.json`, key `sha256`) —
that file already hashes its own sample files, so this field is a transcription,
not a new practice.

**Size, measured.** That entry, canonicalised the way
`edgar_warehouse/mdm/clean/store.py:23-30` canonicalises a body, is **923 bytes**.
Eight kinds × three rules × two verdicts = 48 entries ≈ **44 KB** — negligible
against `commit_batch`'s 16 MB request cap
(`edgar_warehouse/mdm/migrations/023_clean_mdm.sql:125`), which matters because the
digest and body travel into every publication payload (`023:186-191`).

### The exact check the Merge Stage performs

A pure function of the body — no I/O, no clock, so it reproduces identically on
replay. Run it in `register_policy` (authoring time, where the operator meets it)
**and** at `merge.py:183` (every batch, as the backstop for a row inserted around
`register_policy`):

```
qualified(body):
  for entry in body["automatic_rules"]:
      rule = body["kinds"][entry["kind"]][entry["family"]]["rules"][entry["rule_id"]]   # must exist
      require rule["version"] == entry["rule_version"]                                   # (ii) orphan check
      require entry["verdict"] in rule["emits"]
      bar = body["kinds"][entry["kind"]]["bars"][entry["family"]]                        # must exist — no default
      p = entry["proof"]
      require p["method"] == bar["method"] and p["one_sided_confidence"] == bar["one_sided_confidence"]
      require isinstance(p["n"], int) and p["n"] > 0 and 0 <= p["correct"] <= p["n"]
      require abs(wilson_lower_bound(p["correct"], p["n"], p["one_sided_confidence"]) - p["lower_bound"]) <= 1e-9
      require p["lower_bound"] >= bar["min_precision"]                                    # (iii) bar arithmetic
      require p["adversarial"]["violations"] == 0 and p["adversarial"]["fixture_sha256"]
      require p["approved_by"] and p["approved_at"] parses as an instant and p["reason"]
      require p["cohort"]["files"] is a non-empty {name: sha256} map
      # no duplicate (kind, family, rule_id, verdict) entries
```

`merge.py:183-184` changes from a blanket truthiness refusal to
`if policy is None or not qualified(policy): raise Conflict(...)` — the same
line, a predicate instead of `bool`. `store.py:155-156` changes the same way.
Codex owns both.

What the check **cannot** do, stated plainly: it verifies that the arithmetic is
self-consistent and clears the bar, not that the numbers are true. A fabricated
`n: 1000, correct: 1000` passes. The defences against that are not code:
`approved_by`/`approved_at`/`reason` are durably attributed in an append-only
table (`023:102-103`), the sample hashes are recorded, and a CI job outside the
Merge Stage can re-score the named files and compare. Say this to Codex rather
than implying the predicate is a truth check.

### What activation does *not* cover

Q11's bar is about *automatic binding/consolidation decisions*
(`docs/specs/clean-mdm/merge-stage.md:53-57`). Field survivorship has no
precision bar and needs no activation entry — a field rule is live the moment its
kind section declares it (`survivorship.py:200-203`). Only the Classification and
Binding/Consolidation families take `automatic_rules` entries.

## 3. Clean MDM constraints and reusable pieces

| Constraint / reusable piece | Evidence |
| --- | --- |
| **`automatic_rules` is refused today by truthiness, in two places** — the whole Q16 boundary is these two lines | `edgar_warehouse/mdm/clean/merge.py:183-184` (`policy is None or policy.get("automatic_rules")` → `Conflict`); `store.py:155-156` (`register_policy` raises "No qualified automatic matching rules are installed"). `merge.py:4` docstring: "Neither auto binding nor automatic consolidation is enabled in this release." |
| The word *qualified* is already in the code's own error string — the intended future is a predicate, not a permanent ban | `store.py:156`; Q16 `merge-stage.md:196-202` ("numeric calibration and versioned policy evidence are mandatory before each automatic rule activation") |
| **Clean MDM's existing idiom is already option (a): copy the external authority's evidence *into* the immutable body, then re-verify it on every commit** — this is the single strongest precedent for the recommendation | `store.py:205` (`body = {**body, "registry_evidence": authority[0]}` inside `register_dataset`); re-checked at every batch in `023_clean_mdm.sql:155-158` (status `active`, matching `version_id`, matching `source_family`) |
| The policy row is immutable and the digest is `sha256` of the whole canonical body — a proof inside it cannot drift from the rule it activates | `023:102-103` (append-only trigger over `policy` among others); `store.py:33-34`, `store.py:164` |
| One batch pins one digest by FK; an old batch replays under the policy it pinned | `023:24`; `merge.py:179-184`; re-running a `batch_id` returns the stored effects rather than recomputing (`merge.py:173-178`) |
| **Who activates is already answered by privilege, not by a new role**: policy registration is owner-only and the runtime cannot change policy activation | `store.py:154` docstring ("Migration/governance owner only; runtime has no INSERT privilege"); `store.py:105-145` (runtime gets `SELECT` + four `EXECUTE` grants, and the migration *asserts* it has no INSERT/UPDATE/DELETE); `docs/specs/clean-mdm/recovery.md:111`; `docs/specs/clean-mdm/local-operations.md:40-42` ("Do not manufacture activation authority to make a run pass") |
| Steward overrides already carry reviewer / reason / evidence / scope / expiry, hashed into their own id — the proof block reuses this vocabulary so the operator reads one idiom | `evidence.py:155-166` (`decision()`: `actor`, `reason`, `at`, `decision_id = digest(body)`); `023:175-177` (commit refuses a decision without actor and reason); `identity.py:116-119` (override requires `evidence`; honours `expires_at` against `as_of`); scope is the override's `subject`/`field`/`profile_id`, matched at `survivorship.py:228-232`; `merge-stage.md:151-157` |
| "Do not invent automatic expiry schedules" — so the proof gets **no** default expiry | `merge-stage.md:155-157` |
| A policy change mid-batch is already a rejected stale activation; policy upgrades are explicit replay operations | `recovery.md:102`; `merge-stage.md:192-194` |
| The bar is per `(entity kind, rule family)` in the accepted policy — matching the per-kind `bars` block above | `merge-stage.md:53-57`; `docs/specs/clean-mdm/acceptance.md:40` |
| Zero hard-veto violations in adversarial fixtures, plus *measured* recall and review volume, are part of the same gate | `merge-stage.md:57-58`; `acceptance.md:40` |
| The `fields` block is already keyed by kind, and the digest is stamped on every selected field | `company_source.py:62-72`; `survivorship.py:200`, `:274` |

**Is there an existing calibration or evidence table that (b)/(c) could reuse?
No.** The full `mdm_v2` object list is `migration`, `policy`, `dataset`, `batch`,
`observation`, `checkpoint`, `assertion`, `identity`, `decision`, `projection`,
`publication`, `publication_event` (`023:5-93`), plus `attempt_event`
(`026_clean_mdm_attempts.sql:2-11`), `deferred_record`
(`027_clean_mdm_deferred.sql:2-10`) and the Change-Ledger-side `mdm_mirror.event`
(`024_clean_mdm_mirror.sql:6-12`). None stores a measurement. Nor does the
Change Ledger side: the acquisition tables in `013_acquisition_ledger.sql`
(`source_observation_cursor`, `source_fetch_decision`, `source_fetch_work`,
`source_fetch_transition`, `source_revision`, `source_processing_decision`,
`source_expected_producer`), `015_source_evidence_conflict.sql`
(`source_evidence_conflict`) and `017_source_exclusion_and_evidence_import.sql`
(`source_evidence_import`) carry authorization references, reasons and hashes but
no precision, recall, sample-size or confidence column — a grep for
`precision|recall|sample_size|confidence|lower_bound|accuracy|measur` across
013–017 and for `calibrat` across `edgar_warehouse/mdm/clean/` and
`edgar_warehouse/mdm/migrations/` returns nothing. The Change Ledger's
`source_registry_version` (`014_source_registry.sql:49-67`) is the closest
*shape* in the repo — `status IN ('draft','activation_blocked','active','superseded')`,
a NOT NULL `operator_authorization_reference`, a `blocker`/`next_action` pair
required when blocked, and a single-active partial unique index (`014:73-75`).
It is worth reading as "what (b) would cost": a table, a four-state machine, a
uniqueness index and a migration — all to provide what one immutable hashed body
already provides.

## 4. What the two existing proofs contained, and how big a proof block is

Both proofs are on disk under `.scratch/person-consumer-contract/research/`.

| Artifact | Bytes | Rows |
| --- | --- | --- |
| `18-owners.jsonl` (the scored population) | 11,818,173 | 5,743 |
| `18-sample.jsonl` (the labelled sample, 44 fields per row) | 1,974,910 | 1,220 |
| `18-summary.json` (every count, the scored rule table, the hashes) | 315,641 | — |
| `18-extension-sample.jsonl` / `-summary.json` / `-stats.json` | 464,258 / 92,571 / 1,821 | 160 |
| `18-classify.py` (the scoring script) | 51,382 | — |
| `18-sample-plan.json` (population and sample size per stratum) | 1,712 | — |
| `16-sample.jsonl` / `16-results.jsonl` / `16-iapd-requests.jsonl` | 90,352 / 188,697 / 40,687 | 248 / 267 / 273 |
| `16-summary.json` | 26,243 | — |
| **Total** | **≈ 15.1 MB** | — |

**The fields a proof actually needed.** Research 18's summary carries
`n_rows`, `n_distinct_owners`, `n_labeled`, `n_uncertain`,
`wilson_n_for_99_lcb_zero_errors: 381`, the stratified `population_cells_owners`
and `sample_cells` (23 strata each), a `rules` block with per-rule
`decided_person` / `person_correct` / `decided_entity` / `entity_correct` /
`deferred` plus population-weighted variants and an explicit `errors` list with
the reason for each, `labels` (person 851 / entity 369), `label_evidence_class`,
`draft_overrides` (16), `uncertain_cases` (4), and `sha256` of the two evidence
files computed after all writes. Research 16 additionally carries a `requests`
block (273 calls, all 200, first/last timestamps, per-host counts, the 300 cap),
`selection_sql`, and the per-quartile / per-title-class breakdowns that show the
sample was stratified rather than convenience-drawn.

**So: is a proof block small or large?** The *decisive* content is small. Strip
the strata tables, the per-rule scoreboard for the 19 rules that were not chosen,
the error narratives and the label reasons — all of which are the *research*,
not the *claim* — and what activation needs is: method, one-sided confidence, n,
correct, the resulting lower bound, the adversarial-fixture result, the cohort
identity (description, sources, `drawn_at`, seed, population size) and the file
hashes, plus who approved it, when and why. That is **923 canonical bytes**
(§2, measured). The 15 MB stays where it is and is named by hash. An option (b)
table would have to store the same 923 bytes plus its own key and status column;
option (a) stores them where the digest already protects them.

**One discrepancy the proof block must pin, found while re-deriving the numbers.**
Clean MDM's accepted method is "a one-sided 95% lower confidence bound"
(`merge-stage.md:54`, `acceptance.md:40`) — one-sided 95% means z = 1.645.
Research 18 used z = 1.96: its own arithmetic is `n/(n+3.8416)` and
3.8416 = 1.96² (`18-reporting-owner-classification-precision.md:83-85`), which is
the **one-sided 97.5%** constant. The difference is not cosmetic: for a 99% bar
with zero errors, one-sided 97.5% needs **n ≥ 381** while one-sided 95% needs
**n ≥ 268**; for a 99.9% bar, **3,838** versus **2,703** (recomputed here with
`uv run --no-project`; 381 reproduces research 18's own
`wilson_n_for_99_lcb_zero_errors`). Research 18 is therefore *stricter* than the
accepted policy, so its result stands either way — but two proofs written at
different coverage are not comparable, which is why the shape carries a single
`one_sided_confidence` field in both the `bars` declaration and the `proof`, and
the check requires them equal. One field, not a `confidence`/`z` pair, so there
is nothing to contradict. The example above declares 0.975 because that is what
research 18 actually measured; whether Q11's bar should be stated at 0.95 or
0.975 is Codex's and the operator's call, and it should be settled before the
first bar is written down.

## 5. How established tools activate a rule

| Tool | Unit of activation | Who activates | Evidence stored with the config? | URL |
| --- | --- | --- | --- | --- |
| **Informatica Multidomain MDM 10.4** | One **match column rule** inside a match rule set — its position determines the directive: "The manual merge match rule changes to an automerge match rule" when moved up past the line. The rule set itself is the run unit: "Each time the match process is run, only one match rule set is used." | A configuration user in the Hub Console; the change is a metadata edit requiring a write lock, then Save → the "Rule Set Evaluation" dialog. No steward approval step is documented on this path. | **No.** Nothing in the rule carries a measurement; `AutoMergeInd` is a yes/no property. Auto Match and Merge metrics are per-job outputs, not rule attributes. | [match-rule-sets](https://docs.informatica.com/master-data-management/multidomain-mdm/10-4-hotfix-1/configuration-guide/part-4--configuring-the-data-flow/configuring-the-match-process/configuring-match-columns/match-rule-sets.html), [setting-a-match-rule-as-an-automerge-match-rule](https://docs.informatica.com/master-data-management/multidomain-mdm/h2l/0811-match-rule-configuration-example/match-rule-configuration-example/step-8--set-merge-options-for-match-rules/setting-a-match-rule-as-an-automerge-match-rule.html) (both 403 to non-browser clients; read with a browser user agent) |
| **Reltio** | One **match group** inside an entity type's `matchGroups`, via its required `type`: `automatic` = "merge the pair of profiles", `suspect` = "present the profiles to a data steward for review", `relevance_based` = "use user-designed scoring to determine the outcome" with `weights` and `actionThresholds` inside the same rule. | Whoever edits the tenant's metadata configuration — "you will include the matchGroups section within the definition of the entity type in the metadata configuration of your tenant". The docs name no approval role or gate. | **No.** The Match Rule Analyzer profiles rules against tenant data, but its results are fetched from a separate URI by task id, not written back into the configuration. | [the-match-groups-construct](https://docs.reltio.com/en/explore/get-a-crash-course/get-ready-to-turn-your-data-into-action/learn-about-multidomain-mdm/reltio-match-merge-and-survivorship/the-match-groups-construct), [match-rule-analyzer-version-2-dynamic](https://docs.reltio.com/en/developer-resources/entity-management-apis/entity-management-apis-at-a-glance/potential-matches-api/match-rule-analyzer-version-2-dynamic) |
| **Tamr Core** | The **published cluster set** of a mastering project (a "Review and publish clusters" job assigns persistent IDs), plus per-cluster verification, whose options decide whether the model may still move those records: "Verify and Auto-accept Suggestions" vs "Verify and Disable Suggestions". | Curators and verifiers — "Curators periodically 'publish' clusters"; "Curators and verifiers review and validate clusters". | **Yes, partly — the only tool surveyed that does.** "Each time you republish, Tamr Core saves a snapshot of the clusters and recomputes recall and precision metrics", shown over time with confidence intervals. The metrics are bound to the publish event, not to an individual rule. | [overall-workflow-mastering](https://docs.tamr.com/new/docs/overall-workflow-mastering), [curator-publishing-clusters](https://docs.tamr.com/new/docs/curator-publishing-clusters), [verifying-clusters](https://docs.tamr.com/new/docs/verifying-clusters) |
| **Splink** (MoJ) | **No activation concept.** The threshold is an argument at call time: "Pairwise comparisons with a `match_probability` at or above this threshold are matched", passed to `cluster_pairwise_predictions_at_threshold()`, not read from the settings. | Whoever writes the calling code. | **Parameters yes, evidence no.** `save_model_to_json` saves "the configuration and parameters of the linkage model", including the trained `m_probability`/`u_probability` in each comparison level and `probability_two_random_records_match` — learned values, not a measurement of correctness. The evaluation methods (`accuracy_analysis_from_labels_table`, `prediction_errors_from_labels_table`) return charts and dataframes; nothing says their output is persisted into the model. | [clustering](https://moj-analytical-services.github.io/splink/api_docs/linker_clustering.html), [misc](https://moj-analytical-services.github.io/splink/api_docs/misc.html), [settings](https://moj-analytical-services.github.io/splink/topic_guides/splink_fundamentals/settings.html), [evaluation](https://moj-analytical-services.github.io/splink/api_docs/evaluation.html) |
| **Senzing** | The **whole engine configuration**, identified by one `CONFIG_ID`. Registering and activating are explicitly separate: "Registered configurations do not become immediately active nor do they become the default." Promotion is `setDefaultConfigId`, or `replaceDefaultConfigId`, which fails "if the current default configuration ID value is not as expected" — a compare-and-set. | Whoever holds the SDK's config-manager capability; the registry "contains the original timestamp, original comment and configuration ID of all configurations ever registered with the repository", and registrations "cannot be unregistered". | **A free-text comment only.** `registerConfig` takes "an optional comment string to accompany the registered configuration"; there is no measurement field. | [SzConfigManager (Java SDK 4.x)](https://garage.senzing.com/sz-sdk-java/com/senzing/sdk/SzConfigManager.html) |

**What the survey settles.** Three findings transfer directly.

1. **Register ≠ activate is the established split** (Senzing, explicitly; Tamr,
   via publish; Informatica, via rule position). The recommendation's
   "declared rule in the kind section, separate activation entry" is that split.
2. **Compare-and-set on the active identifier is the established safety
   mechanism** (Senzing's `replaceDefaultConfigId`). Clean MDM already has it
   twice over — the pinned `policy_digest` FK (`023:24`) and
   `expected_generation` (`023:139-141`) — so nothing new is needed.
3. **Only Tamr stores the measurement with the activation event**, and it does so
   at the coarsest possible grain (the whole project's recall/precision per
   publish). No surveyed tool binds a precision proof to an individual rule. The
   recommended shape is therefore *stricter* than any of them — which is what
   Q11 and Q16 ask for, and worth saying to Codex so it is not mistaken for
   vendor-standard practice.

## 6. Failure modes

| Failure mode | How the recommended shape handles it |
| --- | --- |
| **A rule active without proof** | An `automatic_rules` entry with no `proof`, or a `proof` missing any required field, fails `qualified()` at `register_policy` — so no digest is ever minted and there is nothing for a batch to pin. `merge.py:183` runs the same predicate as the backstop for a row inserted around `register_policy` by the owner. Fail-closed at both ends, which is the current behaviour generalised, not weakened. |
| **A proof for an older rule version** | Structurally impossible to *persist*: the entry names `rule_version`, the rule body carries `version`, and both live in the same hashed body. Editing the rule bumps its version, orphans the entry, and the new document is refused at registration. The operator's fix is the honest one — re-measure, or delete the entry and let the rule go back to review-only. |
| **A bar change (99.9 → 99) that should deactivate rules** | Handled by arithmetic, not bookkeeping: the check is `proof.lower_bound >= bar.min_precision`, recomputed from `n` and `correct` every time. A bar change is an edit to the body, so it mints a new digest and leaves already-pinned batches alone — deactivation applies from the next document forward, which is the correct semantics (`merge-stage.md:192-194`). What the arithmetic removes is the sweep: lowering the bar keeps rules that cleared the stricter one; raising it makes the new document fail registration until the short entries are removed or re-proved. The `method` / `one_sided_confidence` equality requirement stops a bar change from silently comparing numbers computed at different coverage — the 95%-vs-97.5% discrepancy in §4 is exactly this hazard. |
| **Replay of an old batch under a rule later deactivated** | The batch pinned digest D; `mdm_v2.policy` is append-only (`023:102-103`); `merge.py:179-184` loads by digest. D's body still holds the rule *and* its proof, so the replay reproduces the decision the policy of that day authorised — and re-running the same `batch_id` short-circuits to the stored effects (`merge.py:173-178`). Deactivation is a *new* body with a new digest; applying it to old data is a new batch, which is what `merge-stage.md:192-194` already requires ("Policy upgrades are separate explicit replay operations"). One digest, one result, preserved. |
| **An operator editing the document by hand** | Any hand edit re-digests, so every existing pin is unaffected and the edited body must pass `qualified()` before it can be registered at all. The residual risk is a *fabricated* proof, which no arithmetic can detect. Mitigations are attribution and reproducibility, not validation: `approved_by` / `approved_at` / `reason` land in an append-only table and in every publication payload (`023:186-191`), and the `cohort.files` hashes let a CI job re-score the sample and recompute the bound. Recommend that CI job as a follow-up ticket; do not claim the Merge Stage provides it. |
| **The proof's sample becomes unretrievable** (the hashes name files nobody kept) | Not handled by the shape, and worth an explicit decision: research 18's 15 MB currently lives under `.scratch/`, which is not a durable evidence store. Either commit the sample files as release artifacts or write them to bronze S3 and record the object key beside the hash. Flagged in §7. |
| **Cohort drift** — a proof measured in 2026 still gating a rule in 2028 | Deliberately *not* auto-expired: `merge-stage.md:155-157` forbids inventing expiry schedules. `cohort.drawn_at` and `n_population` are recorded so drift is visible, and revalidation is a new policy version. An optional `proof.expires_at`, checked against `as_of` exactly as `identity.py:117-118` checks an override's, is available if Codex wants it — it costs the predicate its purity (it would then depend on `as_of`), so it is offered, not recommended. |
| **A rule applied outside the population it was measured on** | Only partly handled. `cohort.source_codes` and `cohort.description` are declared and human-checkable, but the Merge Stage does not verify at runtime that the records it is deciding come from that cohort. Stated as a limit in §7 rather than papered over. |
| **Two entries activating the same verdict twice** (e.g. a copy-paste with different proofs) | The duplicate check on `(kind, family, rule_id, verdict)` refuses it; without that check the first-listed proof would silently win. |

## 7. What could not be determined

- **What coverage the accepted Q11 means.** `merge-stage.md:54` and
  `acceptance.md:40` say "one-sided 95%"; research 18 measured at one-sided
  97.5%. Both sample-size tables are computed in §4; the choice is Codex's and
  the operator's, not this research's. Until it is settled, the `bars` block must
  carry `one_sided_confidence` explicitly and no proof may omit it.
- **Whether the emitted-verdict split is acceptable to Codex.** Per-verdict
  activation is what Person ticket 03's gates 1 and 2 need, but it implies the
  interpreter can run one rule in two modes for one record set. Nothing in the
  current code forbids it; nothing endorses it either.
- **Where the sample files should durably live.** `.scratch/` is not an evidence
  store, and `mdm_v2` has no artifact table. Bronze S3 (immutable, content-hashed
  by `write_immutable_bytes`) is the obvious candidate but was not verified as
  reachable from a policy-authoring workflow.
- **Whether `qualified()` belongs in `store.py` or a new module.** Both
  `register_policy` and `merge.py` must call it; where it lives is Codex's
  structural call.
- **Runtime cohort enforcement.** Whether the Merge Stage should refuse an
  automatic decision on a record outside `cohort.source_codes` was not designed;
  it needs a per-record check the current `qualified()` deliberately avoids.
- **Senzing entity-type scoping and Reltio's approval roles.** Senzing documents
  one config for the repository without saying whether rules can differ by entity
  type; Reltio's match-group pages name no approver for a `type` change. Both
  recorded as "not stated", not inferred.
- **Informatica's rule-set promotion between environments.** The Hub Console's
  export/import of metadata between Development and Production ORS was not read;
  the pages fetched cover configuring a rule, not promoting one. The 403 pages
  were read with a browser user agent as the ticket directed; Profisee remains
  login-gated and was not surveyed.
- **Whether Tamr's stored precision/recall snapshot is retrievable via API** (so
  it could serve as an external reference implementation of "evidence with the
  config") — the docs describe it in the UI only.
