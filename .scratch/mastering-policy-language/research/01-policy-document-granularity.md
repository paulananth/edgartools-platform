# Research: the unit of one policy document — per kind, per (kind, source), or one for all

Ticket: [01](../issues/01-research-policy-document-granularity.md). Map:
[Mastering Policy Language](../map.md). Date: 2026-09-20. Read against the
`claude/mastering-policy-language` worktree (Clean MDM files read-only; `path:line`
citations are into that tree). Vendor claims cite the vendor's own documentation
page; nothing below rests on a blog post.

## 1. The simple solution

**Write one policy document per identity kind (a Company document, a Person
document), and let the system pin all of them together as one body per batch.**
Inside a kind's document live its binding tiers and thresholds (Tier A–D, the
99% or 99.9% bar), its consolidation rules, and, per field, the ordered list of
sources allowed to supply that field. Classification — deciding whether a source
row is a Person or a Company — is *not* written per kind: it is written once per
source, beside that source's dataset contract, because Clean MDM decides a
record's kind while normalizing the source row, before the policy is even
loaded. The same per-source place holds which of a source's row types may enter
which tier (for example "ADV `DE`/`FE` rows never create a Person"), so the
kind document names tiers and bars, never a source's internals. The reason the pinned unit must be "all kinds together" and not "one
kind" is mechanical, not aesthetic: one Merge Stage batch re-projects every
identity it can reach, and a Person batch reaches Companies through
relationships, so the body it pins has to answer for Company fields too. So:
**author per kind; classify per source; pin the composition.** A Person rule
change re-hashes the pinned composition, and today that new hash is stamped
onto Company fields the next time a Company is touched — cosmetic churn unless
Codex stamps the kind section's own version instead (§2, reason 5).

## 2. Recommendation and reasons

**Recommended unit: (a′)** — option (a) for authoring, with two amendments the
evidence forces:

1. the pinned artifact (`mdm_v2.policy.body`, one digest per batch) is the
   **composition of every kind document** — option (c) at pin time — because
   the code cannot pin anything smaller (reason 1);
2. classification is keyed by **source**, not by kind, and belongs with the
   dataset contract (reason 3). It is not "a section per source inside the
   kind document" as option (a) first sketched it.

Option (b), one document per (kind, source), is ruled out (reasons 2 and 4).

**Reason 1 — one batch's closure spans kinds, so the pinned body must too.**
`MergeStage.apply` loads exactly one policy row by the batch's digest
(`edgar_warehouse/mdm/clean/merge.py:179-184`) and then projects *every*
identity in the affected closure, not just the batch's own subjects
(`merge.py:219-266`), calling `select_fields(identity["kind"], …, policy, …)`
for each (`merge.py:257-266`). The closure crosses kinds by construction: a
Person assertion's `relationships[].target_subject` puts the Company's subject
into `keys` (`merge.py:38-42`, `merge.py:69-74`); the Company's `bind` decision
matches `body->>'subject'=ANY(:keys)` (`merge.py:60-62`); `anchors()` lifts its
`entity_id` into `keys` (`merge.py:21-27`, `merge.py:75-78`); that UUID passes
the filter at `merge.py:91-96` and loads the Company identity at
`merge.py:97-102`. `relationships.project` then requires both endpoints to be
present in the projected dict with `status == 'accepted'`
(`edgar_warehouse/mdm/clean/relationships.py:102-108`). If the pinned body had
no `fields.company` section, `select_fields` would read `{}`
(`edgar_warehouse/mdm/clean/survivorship.py:200`) and silently project the
Company with zero fields, with no review raised. A per-kind *pinned* document is
therefore unsafe; the pinned body must carry every reachable kind.

**Reason 2 — source rank is an ordered list inside a field rule; it cannot be
per-source.** Survivorship sorts eligible claims by
`rule["sources"].index(c["source_code"])` (`survivorship.py:239-249`) after
filtering to `c["source_code"] in rule["sources"]` (`survivorship.py:203`). A
rank is a comparison across sources; the spec keys it as "versioned source rank
for `(identity kind, optional profile type, field)`"
(`docs/specs/clean-mdm/merge-stage.md:127`). Splitting the document by source
would copy the whole ordering into every source's copy. Option (b) dies here on
its own, independent of reason 1.

**Reason 3 — classification is decided per source, before the policy is
consulted.** A record's kind is assigned in `normalize` from the *dataset
contract's* adapter block (`edgar_warehouse/mdm/clean/adapters.py:58-68`:
`kind`, `kind_field`, `kind_values`), which is looked up by `source_code`
(`edgar_warehouse/mdm/clean/cli.py:89-95`) and is a per-source, immutable,
registry-versioned document (`edgar_warehouse/mdm/clean/store.py:174-227`;
`mdm_v2.dataset` is keyed by `source_code`,
`edgar_warehouse/mdm/migrations/023_clean_mdm.sql:15-19`). The kind is then
hashed into `assertion_id` (`edgar_warehouse/mdm/clean/evidence.py:82-90`) —
long before `merge.py:179` loads the policy. The Company adapter today is
exactly this shape: `"kind_field": "entity_type", "kind_values": {"operating":
"company"}` (`edgar_warehouse/mdm/clean/company_source.py:48-49`). Clean MDM's
own spec says the dataset contract carries "supported kinds/roles/fields"
(`docs/specs/clean-mdm/source-evidence.md:21`) and that "`source_code`
identifies a dataset, not a provider or entity kind"
(`source-evidence.md:15-17`). Rule C-J (Person ticket 03) is a richer
`kind_values` — a step list over one source's rows that emits
`person | company | entity_undetermined | deferred` — and belongs in the same
per-source place. This is also what makes the cross-kind row in §5 (C-J step 1
sends a reporting-owner row to *Company*) live in exactly one place: the
Person-workstream rule is a *source* rule whose output is a kind; the Company
document's Tier A "bind by CIK" rule then takes over. Nothing is duplicated.

**Reason 4 — a Person change must not re-version Company's *rules*; the kind
document gives that.** Thresholds are already kind-scoped in the corpus: Person
Tier B auto-binds at ≥ 99% (Person ticket 02, `#4`) against Clean MDM's global
≥ 99.9% (`merge-stage.md:53-57`), sent to Codex as a Person-only amendment
(`.scratch/clean-mdm-person-q11-amendment-proposal/map.md:7-12`). Under (c) as
a single authored file, every Person threshold edit is a Company edit for
review purposes; under (b) the Person threshold would have to be repeated per
source. Per-kind authoring is the only shape where the operator's own decision
("99% for Person only") is one line in one file.

**Reason 5 — the digest is one hash of the whole body, and it is stamped on
every field.** `register_policy` stores `digest(body)` of the whole document
(`store.py:164-171`); `mdm_v2.batch.policy_digest` is one FK to one row
(`023_clean_mdm.sql:24`); `commit_batch` reads `required_consumers` from that
one row (`023_clean_mdm.sql:147`) and writes the digest into the batch row and
every publication payload (`023_clean_mdm.sql:150`, `:187`). `select_fields`
stamps the digest into every selected field (`survivorship.py:270-280`);
`ContractReader` surfaces it as field provenance
(`edgar_warehouse/mdm/clean/consumer.py:41`) and folds the whole projection
body — stamps included — into `business_hash`
(`consumer.py:98`, `consumer.py:150-152`). Consequence: after a Person-only
edit, the next batch that touches a Company stamps the new composite digest on
Company fields and changes that Company's `business_hash` although no Company
rule changed. No code keys rebuild scope or parity off digest equality (grep of
`policy_digest` across `edgar_warehouse/mdm/clean/`: only `merge.py`,
`survivorship.py`, `consumer.py`; `bookkeeping.py`, `publication.py`,
`relationships.py` never read it), so this is provenance churn, not a
correctness fault. To make "a Person change does not re-version Company" hold
*at the digest level*, the kind section should carry its own `version`, and the
interpreter should stamp `(composite_digest, kind_version)` — a one-line change
in `survivorship.py:274` that is Codex's to accept. Until then the operator
reads the kind section's `version`, not the composite digest, as "which
Company policy is this".

**Reason 6 — the established tools agree on the split.** Every surveyed tool
that produces a golden record scopes match rules and survivorship by
*entity type / base object / project*, with source priority as a parameter
inside a per-attribute survivorship rule, never as a per-source document
(§4: Informatica, Reltio, Tamr). The linkage-only tools (Splink, Zingg,
Dedupe) scope everything to one job and have no survivorship at all; Senzing
is the one-config-for-everything counterexample, and it also has no
survivorship. None of the six scopes rules by (entity, source).

**What the `fields` block keyed by kind already implies.** It implies the
*pinned* body is multi-kind — `fields: {company: {…}, person: {…}}` is one
object holding every kind (`company_source.py:66-71`; `survivorship.py:200`),
with a parallel `profile_fields` block keyed by profile role
(`survivorship.py:283-285`), and no `kind` or `source` column on the table
(`023_clean_mdm.sql:10-13`). It says nothing about how the body is *authored*;
combined with reason 1 it says the pinned unit cannot be smaller than all
kinds. It is compatible with (a′) and (c), incompatible with (b).

**Proposed body shape (for the prototype ticket, not decided here).**

```
{
  "version": "<composite version>",
  "automatic_rules": [],                  # must stay empty (store.py:155, merge.py:183)
  "required_consumers": [...],            # policy-wide (store.py:157-163, 023:147)
  "kinds": {
    "company": { "version": "...", "binding": {...tiers, thresholds...},
                 "consolidation": {...}, "fields": {field: {sources:[...], ...}} },
    "person":  { "version": "...", ... }
  },
  "profile_fields": { "adviser": {...}, "audit_firm": {...}, "fund": {...} }
}
```

`fields` stays reachable at `policy["fields"][kind]` (or Codex moves the read
to `kinds[kind].fields`); classification stays in each `mdm_v2.dataset.body.adapter`
as a versioned step list. Whether the *authoring surface* is one repo file per
kind composed by a build step, or one file with one top-level key per kind, is
the map's open "Authoring surface" item; the pinned unit is the same either way.

## 3. Clean MDM constraints, with citations

| Constraint | Evidence |
| --- | --- |
| The policy is pinned **per batch**, one digest, one row | `merge.py:120` (`policy_digest` argument), `merge.py:179-184` (single `SELECT body … WHERE digest=`), `023_clean_mdm.sql:24` (FK on `mdm_v2.batch`), `023:150` (stored on the batch row) |
| One manifest carries one digest for **all** its batches | `cli.py:230` (`manifest["policy_digest"]` copied into every batch command); `company_source.py:190` (`"policy_digest": digest(POLICY)` at manifest level) |
| The digest is `sha256` of the **whole** canonical body | `store.py:33-34`, `store.py:164`; body is JSON object with no kind/source column, `023:10-13` |
| Registration checks only `automatic_rules == []` and `required_consumers` | `store.py:153-171`; `merge.py:183-184` rejects unknown or non-empty-`automatic_rules` bodies; `023:147-148` rejects a missing `required_consumers` |
| `required_consumers` is **policy-wide**, not per kind | `store.py:157`, `023:147`, `023:187-191` (one publication intent per consumer per batch) |
| Survivorship is keyed **kind → field → ordered `sources`** | `survivorship.py:200` (`policy["fields"][kind]`), `:203` (eligibility), `:240` (`rule["sources"].index`), `:205-206` (`clear_sources`), `:216-226` (`allow_unknown_effective`, `max_age_days`); spec `merge-stage.md:122-131`, `:127` |
| Profile survivorship is keyed **role → field** in a sibling block | `survivorship.py:283-285` (`policy["profile_fields"][role]`); roles and their admissible kinds `evidence.py:20-24` |
| The digest is stamped on **every selected field** and surfaced as provenance / business hash | `survivorship.py:274`; `consumer.py:41`, `:83`, `:98`, `:128`, `:150-152` |
| A batch may carry assertions of **several sources and kinds** | Inline `assertions` accepted as-is (`cli.py:75`); each assertion carries its own `source_code` and `kind` (`evidence.py:73-83`); closure gathers all sources (`merge.py:83`); file-input batches are one `source_code` per member (`cli.py:78`, `:90-95`, `:134-137`) but one manifest may hold many batches (`cli.py:53-61`) |
| A batch's **closure** may contain identities of more than one kind | `merge.py:35-42`, `:58-65`, `:69-78`, `:91-105` (chain described in §2, reason 1); `merge.py:219-266` projects all of them; a member whose claim kind ≠ identity kind is a `kind_conflict` review (`merge.py:236-239`); merging two identities of different kinds is refused (`identity.py:94-95`) |
| **Classification** (record → kind) happens in the adapter from the per-source dataset contract, **before** the policy is loaded | `adapters.py:58-68`; contract looked up by `source_code` (`cli.py:89-95`); kind hashed into `assertion_id` (`evidence.py:82-90`); contract is immutable and registry-versioned (`store.py:174-227`; `023:15-19`); Company example `company_source.py:48-49`; spec `source-evidence.md:15-17`, `:21`; `domain-model.md:41-44` ("kind assignment retains its rule and evidence") |
| Supported kinds are a fixed vocabulary in code and DDL | `evidence.py:10-19`; `023:55` |
| Automatic binding/consolidation is disabled; thresholds are per kind and rule family | `merge.py:4`, `:183-184`; `merge-stage.md:53-64` ("for each enabled entity kind and rule family"); Q16 `merge-stage.md:196-202` |
| Policy upgrades are explicit replay operations | `merge-stage.md:92-95`, `:192-194`; `recovery.md:20` (checkpoint carries "contract/policy version") |
| Source rank is never an input to sameness | `merge-stage.md:90` ("Survivor selection does not determine which source wins any master field"); `identity.py:1` docstring; `CONTEXT.md:21-23` (Merge Stage, avoid "identity consolidation by field priority") and `CONTEXT.md:49-51` (Field Survivorship, avoid "source rank as permission to merge identities") |

Net: the code fixes the **pinned** unit (one composite body, all kinds) and
leaves the **authored** unit free; it already keeps per-source configuration in
a different, per-source document (the dataset contract).

## 4. How established tools scope rule configuration

| Tool | Unit of a rule set | Where cross-source rules live | Where survivorship lives | URL |
| --- | --- | --- | --- | --- |
| **Splink** (MoJ) | One settings dict per linkage job / `Linker`; `link_type` is `dedupe_only`, `link_only` or `link_and_dedupe`; `blocking_rules_to_generate_predictions` and `comparisons` are lists inside it ("The type of data linking task. Required.") | The same `comparisons` apply to every input dataset in the job; per-source identity is only a column: "we can't guarantee that the unique id column is globally unique across datasets, so we combine it with a source_dataset column" | **None** — Splink emits pairwise match probabilities and clusters, not golden records; the settings guide has no survivorship or source-priority key | [settings_dict_guide](https://moj-analytical-services.github.io/splink/api_docs/settings_dict_guide.html), [link_type topic guide](https://moj-analytical-services.github.io/splink/topic_guides/splink_fundamentals/link_type.html) |
| **Senzing** | One engine configuration for the whole repository; data sources, feature types and entity types are registered in it ("Senzing normalizes types (features, data sources, etc) into IDs in the database. The Senzing ER configuration maps those IDs to what they actually are") | In the single config: all sources map onto one feature vocabulary ("Only the attributes listed here may appear inside a feature object"); `DATA_SOURCE` + `RECORD_ID` identify a record; `TRUSTED_ID` forces records together across sources | **None** — "Senzing always replaces records"; no golden-record or survivorship rules in the entity specification | [Managing the ER configuration](https://senzing.zendesk.com/hc/en-us/articles/360010784333--Advanced-Managing-the-Senzing-ER-configuration), [Entity specification](https://senzing.com/docs/entity_specification/) |
| **Zingg** | One JSON config per `modelId` ("Identifier for the model. You can train multiple models - say one for customers … and one for households"); one `fieldDefinition` array per config | The `link` phase uses one config across sources: "each record from the first source is matched with all the records from the remaining sources"; output carries `z_cluster` and `z_source` | **None** — the link page assigns cluster ids only; no merged record | [Configuration 0.3.3](https://docs.zingg.ai/0.3.3/stepbystep/configuration), [Field definitions](https://docs.zingg.ai/latest/stepbystep/configuration/field-definitions), [Linking across datasets](https://docs.zingg.ai/latest/stepbystep/link) |
| **Informatica Multidomain MDM 10.4/10.5** | Match rules are configured per **base object**; a match rule set groups match column rules and "Each time the match process is run, only one match rule set is used" | Inside the base object's match rules: "Match rules are configured by setting the conditions for identifying matching records within and across source systems" | Separate from matching, per column per source system: "Trust is enabled and configured at the column level. For example, you can specify a higher trust level for Customer Name in the Orders system and for Phone Number in the Billing system … Trust is used to determine survivorship" | [Match rule sets](https://docs.informatica.com/master-data-management/multidomain-mdm/10-4-hotfix-1/configuration-guide/part-4--configuring-the-data-flow/configuring-the-match-process/configuring-match-columns/match-rule-sets.html), [Match column rules](https://docs.informatica.com/master-data-management/multidomain-mdm/10-4-hotfix-1/configuration-guide/part-4--configuring-the-data-flow/configuring-the-match-process/configuring-match-column-rules-for-match-rule-sets.html), [Trust settings](https://docs.informatica.com/master-data-management/multidomain-mdm/10-5-hotfix-4/configuration-guide/part-4--configuring-the-data-flow/mdm-hub-processes/load-process/trust-settings-and-validation-rules/trust-settings.html) (pages return 403 to non-browser clients; read with a browser user agent) |
| **Reltio** | Match groups per **entity type**: "you will include the matchGroups section within the definition of the entity type in the metadata configuration of your tenant" | Inside the entity type's match groups (`scope` = ALL/INTERNAL/EXTERNAL); sources appear as crosswalks, not as a rule-set unit | Per entity type, per attribute: "Each survivorship group has a mapping of attribute URIs to survivorship strategies"; "One group for a type must be set as default"; source priority is a strategy parameter — `SRC_SYS`: "The user provides a priority list of sources … All crosswalks from a source system with the highest priority become winners" | [Match groups construct](https://docs.reltio.com/en/explore/get-a-crash-course/get-ready-to-turn-your-data-into-action/learn-about-multidomain-mdm/reltio-match-merge-and-survivorship/the-match-groups-construct), [Survivorship groups](https://docs.reltio.com/en/objectives/resolve-potential-matches/potential-matching-at-a-glance/potential-matching-navigation/design-survivorship-rules/survivorship-groups), [Survivorship rules](https://docs.reltio.com/en/objectives/resolve-potential-matches/potential-matching-at-a-glance/potential-matching-navigation/design-survivorship-rules/survivorship-rules) |
| **Tamr Core** | One mastering **project** per logical entity: curators "Identify the single logical entity, such as people, customers, or products, for mastering" | Inside the project's unified dataset: "A mastering project helps organizations find records that refer to the same entity within and across input datasets" | A separate golden-records project over the mastering project's clusters: "Create consolidation rules to aggregate values for each attribute"; "Rules can include dataset prioritization and conditions" | [Mastering projects](https://docs.tamr.com/new/docs/overall-workflow-mastering), [Golden records](https://docs.tamr.com/new/docs/overview-golden-records) |
| **dedupe** (the library behind Dedupe.io) | One `Dedupe` (single dataset) or `RecordLink` (two datasets) object, initialised once with its variable definitions | `RecordLink`: "Use RecordLinkMatching when you have two datasets that you want to join" — the same variables apply to both | Only `dedupe.canonicalize()`, which "Constructs a canonical representation of a duplicate cluster by finding canonical values for each field" — no source priority | [API documentation](https://docs.dedupe.io/en/latest/API-documentation.html) |

Pattern: the three tools that build golden records (Informatica, Reltio, Tamr)
all scope match rules **per entity type** and survivorship **per attribute
within that entity type**, with source priority as a *parameter of the
survivorship rule*. The three linkage tools scope everything **per job** and
have no survivorship. No tool scopes a rule set per (entity, source).

## 5. The corpus of rules already written in this repo

Family: **C** = classification (record → kind), **B** = binding/consolidation
(sameness), **S** = survivorship/projection (values). Scope: **per-source** or
**cross-source** (compares across sources / an ordered source list) or
**per-kind** (a bar or veto that applies to the kind regardless of source).

| # | Rule | Family | Scope | Sources named | Where written |
| --- | --- | --- | --- | --- | --- |
| 1 | Source authority: SEC for filings, financials and SEC identity (CIK authoritative); GLEIF for published legal identity, lifecycle, registration, consolidation and exceptions (LEI additive) — the authority scoping behind row 9's "cannot overwrite SEC" | S (authority, feeds survivorship) | cross-source | SEC, GLEIF | `.scratch/gleif-company-augmentation/spec.md:45-51`; `merge-stage.md:143-149` |
| 2 | A Company-to-LEI binding may go active only as (i) a revalidated Adjudicated Seed Link or (ii) a verified deterministic crosswalk from an authoritative/certified identifier with uniqueness | B | cross-source (SEC Company ↔ GLEIF LEI) | SEC, GLEIF | `spec.md:74-88`; ticket 13 answer |
| 3 | Company tiers: A publishable; B, C Steward-only; D rejected; name match alone never sufficient in any tier | B | per-kind (Company) | GLEIF candidates vs SEC Companies | `spec.md:90-96` |
| 4 | Uniqueness: one active LEI per Company, one active Company per LEI; conflict is a hard veto to review | B | cross-source | SEC, GLEIF | `spec.md:97-98` |
| 5 | Revalidation triggers (changed LEI, mapping, conflict, successor/duplicate/retired, monthly, rule-version); failed link business-closed via `revoke`; successor needs a new decision | B | per-source (GLEIF lifecycle) acting on a cross-source binding | GLEIF | `spec.md:100-104`; ticket 13 |
| 6 | OpenCorporates mapping is corroborating evidence only, never merge authority | B | per-source | GLEIF `opencorporates_lei` | `spec.md:60`, `:245` |
| 7 | Automatic Company matching stays disabled until holdout LCB ≥ 99.9% precision with zero uniqueness violations | B | per-kind (Company; inherits global Q11) | — | `spec.md:110-112`; `merge-stage.md:53-57` |
| 8 | Company projected field set (first slice): LEI/link status, legal form, legal jurisdiction, entity + registration status, registration dates, managing LOU, validation source, registration authority, creation date; names/addresses/legal events/expiration/successor retained as evidence only | S (projection) | per-source (GLEIF fields) inside the Company field set | GLEIF | `spec.md:131-138`; ticket 15 answer |
| 9 | SEC and GLEIF values for different concepts stay parallel (SEC state of incorporation ≠ GLEIF legal jurisdiction); comparable disagreement opens review and cannot overwrite SEC | S | cross-source | SEC, GLEIF | `spec.md:140-148`; ticket 15; `company-completion.md:44-50` |
| 10 | Field selection order: override → versioned source rank → effective time → publication time → stable key; the consumer supplies its versioned rank | S | cross-source (ordered source list per field) | SEC, GLEIF | `spec.md:145-148`; `merge-stage.md:122-131` |
| 11 | Business-close a value only on explicit source change or complete reconciliation; partial-delta absence never retires a value | S | per-source (GLEIF completeness) | GLEIF | ticket 15 answer; `spec.md:203` |
| 12 | One Person, one MDM id; `owner_cik` and ADV `OwnerID` are cross-reference identifiers, never the identity, never a composite key | B | per-kind (Person) | SEC Form 3/4/5, IAPD ADV Schedule A/B | Person ticket 02 answer `#1` |
| 13 | A cross-reference id points at exactly one Person; a second Person claiming a bound id is a hard veto to review | B | cross-source | SEC ownership, ADV | Person 02 `#2` |
| 14 | No Person is created without a match attempt against every existing Person | B | per-kind (Person) | — | Person 02 `#3` |
| 15 | Person Tier A: shared cross-reference id → auto, deterministic | B | cross-source | any source carrying `owner_cik` / `OwnerID` | Person 02 `#4` |
| 16 | Person Tier B: compound context key (same issuer/firm CIK + exact normalized name + consistent role/flag) → auto **once calibrated ≥ 99% LCB**; review-only until then | B | cross-source; **per-kind threshold (99%, not 99.9%)** | SEC ownership, proxy, 8-K, ADV | Person 02 `#4`; calibration ticket 17 (open); Q11 amendment `clean-mdm-person-q11-amendment-proposal/map.md:7-12` |
| 17 | Person Tier C (fuzzy name / cross-issuer name) → Steward via pre-merge candidate table; Tier D → reject | B | per-kind (Person) | — | Person 02 `#4` |
| 18 | ADV `DE`/`FE` rows never create a Person; firm CRD is an Adviser-profile attribute; proxy rows blocked until parser fix; 8-K rows Tier B/C only | C + B | per-source | ADV Schedule A/B, proxy `sec_executive_record`, 8-K | Person 02 `#5-6` |
| 19 | Rule **C-J**, evaluated per owner CIK: step 0 no `submissions.json` → deferred; step 1 SEC `entityType ∈ {operating, investment}` → **company** (bind by CIK, Tier A); step 2 unambiguous legal-form token → entity-undetermined (surname guard → deferred); step 3 no token + structurally empty + person-shaped → **person**; step 4 else → deferred | C | **per-source** (`sec_ownership_reporting_owner` + bronze `submissions.json`); step 1's output crosses to Company | SEC Form 3/4/5 reporting owners | Person ticket 03 `:32-47`; `research/18-classify.py:64-87`, `:139-151`, `:492-495`, `:671-703` |
| 20 | Flags (`is_officer`, `is_director`, `is_ten_percent_owner`, `is_other`) and `entityType='other'` and deputization are evidence, never deciders; 10%-only never coerced to entity | C | per-source | SEC Form 3/4/5 | Person 03 `:49-59` |
| 21 | "Entity, kind undetermined" is terminal for the Person consumer (deferred outside Person scope, no review) | C | per-source | SEC Form 3/4/5 | Person 03 `:60-66` |
| 22 | A kind correction is review + bounded rebuild, never an entity merge | C → B | per-kind (all) | — | Person 03 `:88-90`; `domain-model.md:41-44`; `identity.py:94-95` |
| 23 | Automatic `person` may go live on 841/841; automatic `entity` needs the two post-hoc guards re-measured on the first production cohort | C (activation evidence) | per-source | SEC Form 3/4/5 | Person 03 `:92-97` |
| 24 | Classifier reads bronze `submissions.json`, never a live fetch; edgartools' `is_company` is not reused | C | per-source | SEC | Person 03 `:98-103` |
| 25 | Source category, asserted legal form and inferred kind are stored separately, each with rule id, version and step | C (provenance) | per-source | SEC | Person 03 `:73-86`; `domain-model.md:41-44` |
| 26 | Person field set / privacy / retention | S | per-kind (Person) | — | Person ticket 04 — **open**, nothing written yet |
| 27 | Foundation: identity evidence is "owned per consumer, not here"; survivorship and domain meaning are each consumer's own spec | — (scoping) | per-kind by construction (a consumer = a kind) | — | `docs/specs/mdm-enrichment/shared-foundation.md:69-74`, `:347-350` |
| 28 | Foundation: a publication family is one `source_code` row in `mdm_v2.dataset`; completeness/continuity rules recommended to live in `mdm_v2.dataset.body` | — (per-source contract home) | per-source | GLEIF families | `shared-foundation.md:45-48`, `:192-203` |
| 29 | Clean MDM: per-kind candidate evidence and required guards (Company, Person, Security, Branch/Government/IO, Venue, Fund Structure) | B | per-kind | — | `merge-stage.md:44-51` |
| 30 | Clean MDM: normalization (Unicode, case-fold, whitespace) is a versioned policy; similarity dependency pinned | B (primitive) | global | — | `merge-stage.md:66-71` |
| 31 | Clean MDM: coherent field groups select one source assertion together; freshness limit validated before ranking | S | cross-source | — | `merge-stage.md:137-141`; `survivorship.py:216-226` (`max_age_days`) |
| 32 | Clean MDM: fields without a registered policy remain evidence-only; authority families SEC / IAPD-ADV / PCAOB / GLEIF keep separate namespaces | S | cross-source | SEC, IAPD/ADV, PCAOB, GLEIF | `merge-stage.md:143-149` |
| 33 | Clean MDM: steward override wins first, persists until expiry/revocation; no invented expiry | S | per-kind (all) | — | `merge-stage.md:151-157`; `survivorship.py:228-265` |
| 34 | Installed Company policy: six fields, each `sources: [sec.submissions.company.v1]`, `allow_unknown_effective: true`; consumers journal/export/graph | S | cross-source shape with one source today | SEC submissions | `company_source.py:62-72` |

Reading the table by scope: every **C** rule is per-source (19–25, 18); every
**S** rule with an ordered source list is cross-source and keyed by kind and
field (10, 31, 32, 34); every threshold or veto is per-kind (7, 16, 22, 29,
33); the cross-source **B** rules (2, 4, 13, 15, 16) compare identifiers *of one
kind* across sources and so sit naturally in that kind's document. The one row
that looks cross-kind — 19, step 1 — is a per-source classification whose
output is a kind; it lives with the source, and Company's own Tier A rule
(rows 2–3) takes it from there. The one row that would collide under a single
authored document is 16 (Person 99%) against 7 (Company 99.9%): it is the
operator's own decision and it is kind-scoped.

One split the tiers make visible: a tier's *definition and bar* is per-kind
(rows 3, 15–17), but *which source's rows may enter which tier* is per-source
(row 18: ADV `DE`/`FE` never create a Person, proxy rows blocked, 8-K rows
Tier B/C only; row 6: OpenCorporates never merge authority). That eligibility
belongs beside the source's classification in its dataset contract, exactly as
classification does, so the kind document never has to name a source's
internal row types. Same split, same home; no duplication.

## 6. What could not be determined

- **Whether Codex will stamp a per-kind version.** Reason 5's fix
  (`survivorship.py:274` stamping the kind section's version alongside the
  composite digest) is a Clean MDM code change; this research only shows the
  churn exists and is non-fatal. Until decided, "a Person change does not
  re-version Company" holds for the *authored* kind document but not for the
  digest recorded on Company fields.
- **Whether the map wants classification inside `mdm_v2.policy.body` or in
  `mdm_v2.dataset.body.adapter`.** The code evaluates it from the dataset
  contract before the policy loads; putting the C-J step list in the policy
  body would need the adapter to read the policy too (a code change), and
  would put a per-source rule into a document whose digest is pinned per
  batch. Both homes are per-source; the research recommends the dataset
  contract because it already exists and is already versioned, but the map's
  "Authoring surface" item owns the final call.
- **Splink per-source comparisons.** The settings guide and link-type topic
  guide show one `comparisons` list per job and do not state whether a
  comparison can be conditioned on `source_dataset`; not checked further
  since Splink has no survivorship either way.
- **Senzing entity-type scoping of rules.** The configuration article
  describes one config with data sources and feature types; it does not say
  whether principles/rules can differ by entity type (PERSON vs
  ORGANIZATION). Recorded as "one config for all".
- **Reltio `scope` semantics with respect to sources.** The match-groups page
  defines `scope` as `ALL | INTERNAL | EXTERNAL | NONE` without elaborating how
  crosswalk sources interact with it.
- **Informatica pages return HTTP 403 to non-browser fetchers**; the quoted
  sentences were read with a browser user agent from the URLs given. Reltio,
  Tamr, Zingg, Splink, Senzing and dedupe pages were reachable directly.
  Profisee remains login-gated (as the 2026-09-17 vendor note already found)
  and was not surveyed.
- **Person survivorship (ticket 04) is open**; the corpus has no Person
  field rules yet, so the Person document's `fields` section cannot be
  prototyped until it resolves.
- **Tier B's calibration (Person ticket 17) is open**; row 16 is a declared
  rule with an unmet activation condition, which is exactly the "Activation"
  item the map has not yet specified.
