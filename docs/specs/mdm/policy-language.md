# Mastering Policy Language

Status: proposed to Clean MDM (Codex/Grok) 2026-09-20; **partly implemented
from 2026-09-22** under the
[Company mastering map](../../../.scratch/company-mastering/map.md). Written
from the resolved tickets of the
[Mastering Policy Language](../../../.scratch/mastering-policy-language/map.md)
wayfinder map; every decision below lives in one of those tickets and is
gisted here, never restated at length.

**What is built** (PRs #695, #696 and the policy-runtime branch): the per-kind
and per-role field digests (§8, closing §13 item 1); the versioned primitive
registry and five classification primitives (§5); the classification rule
evaluator (§6); and the Dataset Contract lifecycle the rest rests on. **What
is not**: the binding predicates, the activation bar, the suspension table,
group-aware selection, and the §10 registration checks other than 9 and 10.
The runtime still refuses every `automatic_rules` body, so nothing binds
automatically.

Sections amended after implementation are marked with the date and the
operator decision behind them. Where the code and this document disagree, the
code is what runs and this document is the defect.

## 1. Purpose

Clean MDM's Merge Stage already runs under a **policy document**:
`mdm_v2.policy (digest, body jsonb)` (`edgar_warehouse/mdm/migrations/023_clean_mdm.sql:10-13`),
one immutable body pinned per batch and loaded at
`edgar_warehouse/mdm/clean/merge.py:179-184`. Today that body is a Python
dict (`clean/company_source.py:62-72`) whose only declarative content is
per-field survivorship; its `automatic_rules` list must be empty or the
batch is refused (accepted Q16).

This specification defines **what the body may declare** so that the rules
this platform has so far written by hand — Company/GLEIF binding, Person
rule C-J, Person Tiers A–D, the 99% and 99.9% bars — become **data**:
authored per identity kind and per source, versioned, pinned by the
digest, replayable, and executable by a fixed interpreter over a small
vocabulary of named primitives. Adding a source or retuning a threshold
becomes a document change; adding a new kind of test remains a code change.

Operator's framing (2026-09-20): *"instead of hard coding all of these rules
for de duplication and merging can we create a configuration table for each
entity for each source … 1) de duplication rules, 2) merge rules including
priority of sources and which fields will be in the final entity."*

## 2. Scope

**In**: the schema of `mdm_v2.policy.body` for three rule families
(§4); the twelve-primitive vocabulary and its versioning (§5); rule shapes
for classification, binding/consolidation, survivorship/projection
(§6–§8); activation with its two kinds of proof (§9); the checks a
registration performs (§10); replay and change (§11); worked examples (§12).

**Out**: relationship publication (Clean MDM's own relationship table in
`docs/specs/clean-mdm/domain-model.md`); the interpreter, migrations and
any implementation (Codex/Grok's); reopening accepted Q1–Q16 — this
document gives them a data shape, and where it asks for an amendment it
says so (§13); legacy MDM's `mdm_match_threshold` and normalization seeds,
which are evidence of the need and are being decommissioned with legacy.

## 3. Terms

From `CONTEXT.md`. The operator's "de-duplication" is **Source Record
Binding** (a source record → the identity it describes) and **Identity
Consolidation** (two identities → one surviving identity); the operator's
"merge rules" are **Field Survivorship** plus the projected field set.
Two glossary lines are properties of this language, not preferences:
`Merge Stage` *avoids* "identity consolidation by field priority", and
`Field Survivorship` *avoids* "source rank as permission to merge
identities". **Source priority is never an input to a sameness rule**, and
a registration refuses a document that tries (§10).

New terms this specification introduces, to be added to `CONTEXT.md` when
the proposal is accepted:

- **Mastering Policy**: the versioned, digest-pinned document that declares
  a kind's classification, binding and survivorship rules and the proof
  under which each may act automatically. *Avoid*: a per-source config
  table, a runtime switch, a place to store samples.
- **Identifier Contract**: the declaration, per identifier namespace, of
  who issues the value, how many identities one value may name and how
  many values one identity may carry, the second handle used to detect a
  violation, and the measurement that verified the claim. *Avoid*:
  "the id is unique" as an unstated assumption.

## 4. Document model

### 4.1 One document per identity kind, composed into one pinned body

Author **one Mastering Policy per identity kind** (`person`, `company`, …).
Classification rules sit under the **source** they read; binding and
consolidation rules sit at **kind** level because they compare records
across sources; survivorship sits **per field** with an ordered source
list. The kind documents are **composed** into the single body the Merge
Stage pins.

Why composition is not optional: a batch's closure crosses kinds through
relationships (`clean/merge.py:38-42, 69-78, 97-102`) and every reachable
identity is re-projected under the batch's one digest
(`merge.py:179-184, 219-266`; `clean/survivorship.py:200`), so a body
missing a kind silently projects that kind with zero fields. A per-(kind,
source) document dies on survivorship alone: source rank is an ordered
list inside a per-(kind, field) rule (`survivorship.py:203, 240`;
`docs/specs/clean-mdm/merge-stage.md:127`). Golden-record tools (Informatica,
Reltio, Tamr) scope match rules per entity type and survivorship per
attribute; none scopes by (entity, source).
Evidence: [research 01](../../../.scratch/mastering-policy-language/research/01-policy-document-granularity.md).

### 4.2 Body shape

```json
{
  "version": "edgartools-policy-v3",
  "required_consumers": ["journal", "export", "graph"],
  "kinds": {
    "person":  { "version": "person-2026-09-20",  "bars": {…}, "lists": {…}, "normalizers": {…},
                 "identifiers": {…}, "classification": {…}, "binding": {…}, "fields": {…}, "projection": {…} },
    "company": { "version": "company-2026-09-20", "…": "…" }
  },
  "automatic_rules": [ … ]
}
```

`required_consumers` and `fields` are Clean MDM's existing keys, unchanged.
`kinds.<kind>.version` is the authored kind document's own version, carried
so that a Person-only edit is attributable even though the composite
digest changes (§13, item 1).

### 4.3 Where classification lives

Kind assignment already runs **per source, before the policy loads**:
`clean/adapters.py:72-84` assigns a kind from the dataset contract's
adapter block, looked up by `source_code` at `clean/cli.py:118-124`, and the
result is hashed into `assertion_id` (`clean/evidence.py:80-104`). A
classification rule is therefore authored under its source and must be
reachable from the dataset contract.

**Settled** (operator, 2026-09-23; closes §15 item 2). The rule text lives in
the **kind document**, in its flat `rules` list with `family:
"classification"`, and the dataset contract's adapter block **names one** by
kind, `rule_id` and `version`. The adapter block does not hold rule text.

**The policy is resolved at read time**, beside the dataset contract, because
the decided kind is hashed into `assertion_id` and so is settled when the
record is read and never afterwards. `manifest["policy_digest"]` is already at
the manifest's top level, so the read path reaches the pinned body without a
new input.

Two alternatives were rejected. Deciding the kind later, in the Merge Stage,
is forbidden by the hash: the label is part of the record's identity, so
changing it afterwards would change every id and orphan every decision citing
them. Leaving the adapter's lookup table as the decision-maker and letting the
policy only check the result means the measured rules never run, and an SEC
reporting owner whose only evidence is a name is never classified.

A contract that names no rule keeps the adapter's own kind mapping, which is
how every source registered before this existed keeps working. A contract that
names a rule the policy does not hold is **refused**, not ignored: silently
falling back to the table would defeat the reference.

## 5. The primitive vocabulary

**Structure and parameters in data; primitives in code.** The document
declares steps, order, verdicts, thresholds, token lists, field paths and
source ranks. Code provides a fixed vocabulary of named, versioned tests.
Extracted from the rules already written — nothing speculative added.
Evidence: [research 03](../../../.scratch/mastering-policy-language/research/03-primitive-vocabulary.md).

| Family | Primitive | Parameters | Returns |
| --- | --- | --- | --- |
| shared | `normalize_text` | `field`, policy ref (case, Unicode, punctuation, `&`, suffixes) | normalized string |
| shared | `normalize_identifier` | `field`, namespace format | normalized string or typed refusal |
| classification | `evidence_present` | `document` (declared evidence reference) | bool |
| classification | `field_in_set` | `field`, `values[]` | bool |
| classification | `token_match` | `field`, `normalizer`, `token_list`, `exclude_list?`, **at least one of** `min_count` / `max_count` | bool |
| classification | `name_shape` | `field`, `normalizer`, `min_tokens`, `max_tokens`, `suffix_list`, `forbid_digits{applies_to}`, `forbid_characters{applies_to}` | bool |
| classification | `fields_all_empty` | `fields[]` (declared paths) | bool |
| binding | `identifier_match` | `namespace`, `field`, `normalizer` | matching identity or none |
| binding | `identifier_cardinality` | `namespace` (contract in §7.2) | veto or pass |
| binding | `compound_key_equal` | `components[] {field, normalizer, comparison ∈ exact|consistent}` | bool |
| binding | `name_similarity` | `left`, `right`, `normalizer`, `method@version`, `min_score` | bool |
| survivorship | `select_by_source_rank` | `sources[]` (ordered), `clear_sources[]`, `allow_unknown_effective`, `max_age_days` | winner + retained conflicts |

Why the line sits here: the same words (`TRUST`, `FUND`, `CO`, `HOLDINGS`)
are entity *evidence* in rule C-J (`18-classify.py:64-80`) and are
*deleted* by the legacy normalizer (`002_seed_data.sql:73-98`) — one
primitive, two declared lists, opposite uses. Survivorship needs one
primitive because Clean MDM's accepted five-step order
(`merge-stage.md:123-130`) is fixed; the document supplies only the rank
list and eligibility parameters.

**What the vocabulary cannot express**, by design: document-supplied
regular expressions or SQL, clock or network reads, loops, `OR` inside a
step (first-match ordering over steps is how an *unless* is written).
Each would make a pinned digest fail to reproduce a result.

**Versioning.** Every primitive is referenced `name@version`
(`token_match@1`, `normalize_text@edgar-conformed-v1`,
`name_similarity@jaro_winkler-jellyfish-1.0.3`). The interpreter holds a
registry keyed by that pair and **refuses a body naming a pair it does not
have** — at registration (`clean/store.py:155-156`) and per batch
(`merge.py:183-184`). A list or threshold edit needs no primitive bump: it
re-digests the body. A corrected primitive is a **new version**; the old
one is never modified in place. A pinned third-party dependency is part of
the version string (`merge-stage.md:67`: "pin the similarity dependency
*and* algorithm"). Stated plainly: **the digest pins the document, not the
code it names** — exact replay of an old batch needs the old
implementation still in the build, so superseded primitive versions are
retained, the same bargain `merge-stage.md:100-104` strikes for decision
history.

## 6. Classification rules

```json
{
  "rule_id": "C-J", "version": "2026-09-20", "family": "classification",
  "source": "sec.ownership_reporting_owner", "evaluated_per": "sec.owner_cik",
  "emits": ["person", "company", "entity_undetermined", "deferred"],
  "steps": [
    { "step": "0", "verdict": "deferred", "when": [ { "primitive": "evidence_present@1", "negate": true,
                                                       "args": { "document": "sec.submissions.owner" } } ] },
    { "step": "1", "verdict": "company",  "when": [ { "primitive": "field_in_set@1",
                                                       "args": { "field": "sec.submissions.entityType", "values": ["operating", "investment"] } } ] },
    { "step": "2-guard", "verdict": "deferred", "when": [ "token_match (exactly one)", "name_shape", "fields_all_empty" ] },
    { "step": "2", "verdict": "entity_undetermined", "when": [ "token_match (unambiguous, ≥ 1)" ] },
    { "step": "3", "verdict": "person", "when": [ "not token_match", "fields_all_empty", "name_shape" ] },
    { "step": "4", "verdict": "deferred", "otherwise": true }
  ],
  "evidence_recorded": ["sec.submissions.entityType", "structural_fields", "entity_tokens", "person_name_shape", "deputization_text", "flags"]
}
```

Rules:

- Steps are evaluated in listed order; the **first step whose `when` list
  holds entirely** supplies the verdict. A `when` list is a conjunction.
- The catch-all is written `"otherwise": true`, never an empty `when`
  (prototype finding 3; an empty list reads as "always true" and is easy to
  mis-edit by hand). A rule without a catch-all is refused.
- `evaluated_per` names the key one verdict is computed for; every record
  carrying that key receives it.
- `evidence_recorded` names what is written to the assertion regardless of
  verdict. Source category, asserted legal form and inferred kind are
  stored **separately** with the rule id, version and step that fired
  (`domain-model.md:41-44`). A kind correction is review plus bounded
  rebuild, never an entity merge.

  **Where that goes** (operator, 2026-09-23): in the assertion's
  `provenance` block, which is part of the hashed body
  (`clean/evidence.py:80-104`), so a record explains what labelled it with no
  lookup elsewhere. This adds no churn, which is what makes the hash the right
  place: the recorded rule can change in only three ways, and none creates a
  row something else was not already creating. A contract pointing at a
  different rule version is a contract change, which already mints a new
  `mapping_version` and so a new id. The same version carrying different steps
  is refused at registration (§10 check 9). The step that fired is a function
  of the rule and the record, so it cannot move while both are fixed.

  Rejected: a table outside the hash. It leaves the id untouched but costs a
  join to answer "what labelled this?", and breaks the self-describing
  evidence the mapping-version work established.

  Records written before this exists carry no rule identity and are immutable.
  Absence therefore means "decided by the adapter's lookup table, before
  governed rules existed", on the same convention as an absent
  `mapping_version` meaning the first reading.

- A step whose verdict decides no kind (`deferred`, `entity_undetermined`)
  may name a **`probable_kind`**: the kind a record it holds back probably is
  (`CONTEXT.md`, Probable Kind; operator, 2026-09-25). It sorts the Stage and
  never creates an identity; that kind's own rule decides, at its own bar. So
  it carries no proof and no activation. A step that decides a kind may not
  name one, and the value must be a kind. A kind verdict the policy has not
  switched on is its own Probable Kind. The waiting record keeps it as
  `probable_kind`, written only when known, so a record given none keeps its
  id; a record given one waits differently when its publication is re-read,
  and so collides, the limit accepted on 2026-09-23. `mdm_v2.stage_waiting`
  lists the waiting records with it (migration 036). A contract that states kinds by a lookup table may name the Probable
  Kind of the values it does not accept in `probable_kind_values` (GLEIF:
  `FUND` → `fund_structure`, `BRANCH` → `branch`,
  `RESIDENT_GOVERNMENT_ENTITY` → `government`, `INTERNATIONAL_ORGANIZATION` →
  `international_organization`; `SOLE_PROPRIETOR` is left unnamed). A
  record outside the approved Company scope still carries the kind its
  category names.

- **`min_count` or `max_count` is required on `token_match`** (§5). Without
  one, the primitive returns true whatever the name holds, which is a
  fail-open in the test that decides an entity's kind. All three calls in the
  accepted Person document supply a count, so requiring it changes no measured
  result.
- Declared lists must carry `AND`, not `&`: EDGAR conformed names
  normalize the ampersand (prototype finding 4). A registration validates
  declared lists against the named normalizer. `token_match` also counts a
  raw `&` as one token of its own, but only for a list that carries `AND`:
  such a list asks whether a name joins two parties (ticket 12; counting it
  for every list held back McCormick & Co at a fund-name step).
- A verdict may be `automatic` only for `(rule_id, version, verdict)`
  entries in `automatic_rules` (§9). Every other verdict is Steward review.

Rule C-J in full, with its 125 legal-form tokens, ambiguous and suffix
lists and six structural field paths as parameters:
[`prototype/policy-person.json`](../../../.scratch/mastering-policy-language/prototype/policy-person.json).
Its decision and measurement:
[Person ticket 03](../../../.scratch/person-consumer-contract/issues/03-decide-reporting-owner-classification.md),
[research 18](../../../.scratch/person-consumer-contract/research/18-reporting-owner-classification-precision.md).

## 7. Binding and consolidation rules

### 7.1 Shape

```json
{
  "rule_id": "person-tier-a-owner-cik", "version": "2026-09-20", "family": "binding",
  "source": "sec.ownership_reporting_owner", "applies_to_verdict": "person", "emits": ["bind"],
  "when": [
    { "primitive": "identifier_match@1",       "args": { "namespace": "sec.cik", "field": "owner_cik", "normalizer": "normalize_identifier@sec-cik-v1" } },
    { "primitive": "identifier_cardinality@1", "args": { "namespace": "sec.cik" } }
  ]
}
```

- `applies_to_verdict` restricts the rule to records a classification rule
  has given that kind; a binding rule never runs on a `deferred` or
  `entity_undetermined` record.
- `emits` is `bind` (Source Record Binding), `consolidate` (Identity
  Consolidation) or `review`. Tier C (fuzzy) emits `review` and is
  refused if it tries to emit `bind` on `name_similarity` alone (§10).
- A binding rule may not call `select_by_source_rank` (§3).
- Person Tiers A–D as written:
  [ticket 02](../../../.scratch/person-consumer-contract/issues/02-decide-what-binds-a-person.md).
  Company/GLEIF binding as written:
  [GLEIF consumer spec](../../../.scratch/gleif-company-augmentation/spec.md).

### 7.2 The Identifier Contract

Declared once per namespace under `kinds.<kind>.identifiers`. This is
where Clean MDM's *"Exclusivity is policy-specific"*
(`domain-model.md:46-48`) is made concrete.

| Field | Meaning | `sec.cik` (Person) | `crd.individual` (Person) |
| --- | --- | --- | --- |
| `authority` | issuer of the value | SEC/EDGAR | FINRA/IARD |
| `normalizer` | `name@version` | `normalize_identifier@sec-cik-v1` | `normalize_identifier@crd-v1` |
| `claim.forward` | one value → at most N identities | **1** | **1** |
| `claim.reverse` | one identity → at most N values | unbounded (cross-reference ids) | unbounded; duplicates measured ~12/10k |
| `compatibility` | the second handle the runtime veto compares: `field`, `predicate@version` | `owner_name`, `name_compatible@lenient-v1` | `name`, same |
| `verification` | the measurement that earned activation: counts, bound, corpus hash, who/when | 0/72,981 decisions, Wilson UB 0.53/10k; reverse 0/16,677 same-issuer pairs | research 16 figures; forward only |
| `tolerance` | §9.3 | `{unit: items, warm_up_decisions: 10000, max_per_10k: 5}` | same |

Why `sec.cik` can make its claim: EDGAR discards any filer-supplied
reporting-owner name and inserts the CIK's registered name (Ownership XML
Technical Specification v5.1 §4.3.2), so a name difference on one CIK is a
registered-account event; 0 genuine "one CIK, two people" in 104,970 rows.
Why `crd.individual` cannot claim the reverse: research 16. The two Tier A
rules differ in contract, not just namespace.
Evidence: [research 07](../../../.scratch/mastering-policy-language/research/07-owner-cik-cardinality-and-deterministic-binding.md),
[ticket 06](../../../.scratch/mastering-policy-language/issues/06-decide-how-a-deterministic-rule-activates.md).

Reverse-direction hits (an identity would acquire a second value) are
reported as **consolidation candidates**, never vetoed — an identity holds
any number of cross-reference ids. Collapsing them is Identity
Consolidation with its own evidence.

## 8. Survivorship and projection

Clean MDM's existing `fields` block is the survivorship declaration and is
kept as is: per kind, per field, an ordered `sources` list plus
eligibility (`clear_sources`, `allow_unknown_effective`, `max_age_days`),
under the accepted five-step order (`merge-stage.md:123-130`). **Implemented
2026-09-23** at `clean/survivorship.py`, where it moved under `kinds.<kind>`;
bodies registered under the old top-level `fields` block keep working and a
body carrying both is refused.

**What a field's recorded digest covers** (implemented; amends §13 item 1). A
selected field records its **kind's** digest, not the whole body's, with the
authored kind version beside it — so a Person-only edit leaves every Company
value unchanged. That digest covers only the sections of the kind block that
decide **which claim wins**, named in `survivorship.AUTHORITY_SECTIONS`, not
the block whole: `rules`, `bars`, `lists`, `normalizers`, `identifiers` and
`projection` land in the same block and none of them changes a field's winner,
so digesting the block whole would reintroduce the churn one level down. An
undeclared section is refused by name (§10 check 10).

**A profile field records its role's digest**, not the enclosing kind's. A
role attaches to several kinds — `adviser` to company and person, `fund` to
company and fund structure — so its rules stay in one top-level
`profile_fields` block rather than being written once per kind and left to
drift, and its values record a digest computed from that role's own rules,
with the role name carried alongside. Recording the kind's digest made an edit
to a role's rules invisible: it moved no recorded digest anywhere.

**A kind-level default** (implemented 2026-09-24, operator): `kinds.<kind>.defaults`
is a field rule every field of the kind inherits, so the master takes **every
field any source supplies** and the ordered `sources` list decides only where
several supply one. A field declared under `fields` inherits the default and
may override any part of it, such as its own source order. `defaults` is an
authority section. The kind documents live one file per kind in
`edgar_warehouse/mdm/policies/`.

This document adds:

- `primitive: "select_by_source_rank@1"` named explicitly per field, so
  the version is pinned like every other primitive.
- `field_group: [...]` for coherent groups (address components) that must
  select from one claim together — **accepted policy with no
  implementation** (`merge-stage.md:137-139`; `survivorship.py` is strictly
  per-field). Raised for Codex (§13, item 3).
- `projection: { fields: [...], evidence_only: [...] }` per kind — which
  fields the final entity exposes and which are retained as evidence only.
  The Person field set waits on the Person map's own field/privacy ticket
  (§15, item 4).

The Company example (SEC authoritative, GLEIF additive; a comparable GLEIF
disagreement never overwrites an SEC value):
[`prototype/policy-company.json`](../../../.scratch/mastering-policy-language/prototype/policy-company.json).

## 9. Activation

A rule in the document is **declared** (it fires; its result goes to a
Steward) until an `automatic_rules` entry makes one of its verdicts
**active** (it fires; the Merge Stage binds or classifies alone).
**Activation is per `(rule_id, rule_version, verdict)`, never per rule.**
This is what lets C-J's `person` verdict run automatically while its
`entity_undetermined` verdict stays review-only — Person ticket 03's
release gates 1 and 2 as data. No new table, no status column, no new
role: policy registration is already owner-only and the runtime is already
forbidden to change activation (`docs/specs/clean-mdm/recovery.md:51, 111`).
Evidence: [research 02](../../../.scratch/mastering-policy-language/research/02-rule-activation-and-proof.md).

### 9.1 Bars

Declared per `(kind, family)` under `kinds.<kind>.bars`:
`{ "min_precision": 0.99, "method": "wilson_lower_bound", "one_sided_confidence": 0.975 }`.
Person classification is 0.99 (operator amendment, proposed to Codex).
Company classification is 0.95 at 95% one-sided confidence (confidence bands,
`docs/specs/clean-mdm/company-policy.md`, 2026-09-24); merging two published
Company IDs keeps 0.999 (Q11). The accepted floor is kept per **(kind,
family)** (`activation.ACCEPTED_BARS`), so lowering one decision never lowers
another; a pair with no accepted floor cannot declare a bar. A rule with no
bar for its family cannot be activated.

### 9.2 `measured` activation

```json
{ "kind": "person", "family": "classification", "rule_id": "C-J", "rule_version": "2026-09-20", "verdict": "person",
  "activation": "measured",
  "proof": { "method": "wilson_lower_bound", "one_sided_confidence": 0.975, "n": 841, "correct": 841, "lower_bound": 0.99545,
             "adversarial": { "fixture_sha256": "…", "violations": 0 },
             "cohort": { "description": "…", "source_codes": ["…"], "drawn_at": "…", "seed": "20260920", "n_population": 4831,
                         "files": { "18-sample.jsonl": "87209b16…", "18-owners.jsonl": "8181e1bf…", "18-classify.py": "…" } },
             "approved_by": "operator", "approved_at": "2026-09-20T…", "reason": "research 18, C-J person arm" } }
```

The proof travels **inside the body next to the rule** (~923 canonical
bytes); labelled samples stay outside as files named by SHA-256. The Merge
Stage check is a pure predicate over the body:

```
for entry in automatic_rules:
    rule = kinds[kind][family].rules[rule_id]            # must exist
    require rule.version == entry.rule_version            # a rule edited after its proof is orphaned
    require entry.verdict in rule.emits
    bar = kinds[kind].bars[family]                        # no default
    require proof.method == bar.method and proof.one_sided_confidence == bar.one_sided_confidence
    require recompute(proof) == proof.lower_bound and proof.lower_bound >= bar.min_precision
    require proof.adversarial.violations == 0 and proof.cohort.files non-empty
    require approved_by, approved_at, reason
```

replacing the truthiness refusal at `merge.py:183-184` and
`store.py:155-156`. Stated plainly: **the check verifies arithmetic, not
truth** — a fabricated `n: 1000, correct: 1000` passes. The defences are
attribution (append-only, in every publication payload) and a CI job
outside the Merge Stage that re-scores the named files.

### 9.3 `deterministic` activation

A rule whose `when` is identifier primitives only has no precision to
measure; its failure mode is a wrong **identifier contract**, not a wrong
score. Its activation entry names `"activation": "deterministic"` and the
predicate checks instead that every namespace the rule names has a
contract (§7.2) with `claim.forward`, `compatibility` (predicate, version,
**field**), `verification` with a corpus hash, and a complete `tolerance`
block, and that every named primitive resolves.

**Runtime behaviour when the claim is violated** (ticket 06, Q2 = defer and
count, tuned on research 07):

- **Detect**: `identifier_cardinality` resolves the incoming id to an
  existing identity and compares the incoming `compatibility.field` with
  the names already on it using the declared predicate. A "materially
  new" name is the candidate violation. This is a heuristic inside a
  deterministic rule and is declared and versioned for that reason.
- **Defer** the violating record to the Steward; the rule keeps running.
- **Count distinct `(identifier, incoming normalized name)` items**, not
  records — one prolific filer with one typo'd registered name is
  otherwise a burst (27 records for one typo in the corpus).
- **Line**: `warm_up_decisions: 10000`, `max_per_10k: 5`. Measured: never
  trips on 72,981 real decisions; stopped an injected bulk failure within
  8–48 decisions where defer-only silently minted 291 bogus Persons, and
  deactivate-on-first-violation died at decision 3,107 on a middle initial.
- **Deactivate** when the rate crosses the line after warm-up: the
  automatic verdict is withdrawn for the rest of the batch and thereafter;
  review until a new document with a fresh verification is registered;
  recorded as evidence against the contract in the batch's commit evidence.
- **A Steward resolution must record the alias**, or the same item recurs
  on every later filing.

Limits: the runtime can see only name-mismatch alarms, every one of which
was false on real data; a different person with a compatible name is
invisible to any runtime check — the contract's verification guards
against that, not the runtime. The tolerance is tuned on one failure shape.

## 10. Checks a registration performs

Fail closed, in `store.register_policy` and again per batch. A refused
document never becomes a digest.

1. Every `primitive` is a registered `name@version`.
2. Every classification rule has exactly one `otherwise` step and every
   step names a verdict in `emits`; a `probable_kind` is a kind, on a step
   that decides none.
3. Declared lists are valid under their named normalizer (`&` → `AND`).
4. A binding rule calls no survivorship primitive.
5. A binding rule emitting `bind` does not rest on `name_similarity` alone.
6. Every `automatic_rules` entry satisfies §9.2 or §9.3; no duplicate
   `(kind, family, rule_id, verdict)`.
7. Every namespace an activated deterministic rule names has a complete
   Identifier Contract.
8. Every kind that any relationship in the body can reach is present in
   `kinds` (§4.1 — a missing kind projects zero fields).
9. **A rule version names one exact set of steps.** A body whose rule reuses
   a `(kind, rule_id, version)` that an already-registered body holds with
   **different steps** is refused (operator, 2026-09-23). Without this, two
   digests can each hold `C-J@2026-09-20` with different steps, and the same
   record classifies differently with no trace: the per-kind digest cannot
   catch it, because `rules` is deliberately non-authority (§8) and so is
   guaranteed not to move when a rule changes.

   **There is no testing exemption, and none is needed.** A new version is
   already free: nothing is overwritten, a changed body is simply a new digest
   beside the old, and an author may register as many as they like. The check
   refuses one narrow case — two different sets of steps sharing one version
   name — so working freely costs one edit to a version string. Records
   written during a trial are real records in a real store, so a reused
   version corrupts that trial's own evidence; and a check that can silently
   not run makes a failure and a success look identical.

   Draft lifecycle belongs in the **Rules Database**, which holds every
   version with its state (draft, proven, active, retired) and hands Clean MDM
   an *active* one. `CONTEXT.md` says explicitly to avoid editing rules in the
   production MDM database.
10. **A kind block declares every section it carries** as authority-bearing or
    not (§8). An undeclared section is refused by name, so adding one is a
    decision an author makes rather than a silent change to every field's
    recorded authority.

**Implemented 2026-09-24** in `clean/activation.py`: checks 1, 2 and 6 and
the §9.2 predicate, at registration, again per batch and again when a read
path runs a named rule; check 9 at registration only, since it compares
against the bodies already registered. Each kind's accepted bar is a floor the
document may raise but not lower. Check 9 compares the **whole rule**, not only
its steps: an `emits` or `source` change under one version reclassifies records
as surely as a step change. Check 1 verifies each primitive is registered and
of the rule's family; its arguments are still checked when a record reaches
it. Binding rules and
`deterministic` activation are refused by name until company mastering ticket
04 brings the identifier primitives. Check 3 is not built.

The prototype's `validate()` implements 1, 4, 5, 6 and refuses six abuse
cases: a rule edited after its proof, a bar raised above the proof, a
proof at a different confidence coverage, a fabricated lower bound,
activating a verdict the rule cannot emit, and a similarity-only bind.

## 11. Change and replay

- A batch pins one digest; replaying it uses that body and the primitive
  versions it names, so it reproduces the decision that day's policy
  authorised. Old primitive versions are retained (§5).
- Any edit mints a new digest. A rule edit changes `rule.version` and
  orphans its activation entry; the rule silently falls back to review
  rather than inheriting a proof measured on its predecessor.
- A bar change re-runs the arithmetic on registration; every rule that no
  longer clears it is refused. Nobody hunts for what a bar change
  invalidated.
- Which identities a re-registration must re-project is **Open**
  (§15, item 1); bounded rebuild per `merge-stage.md` is the expected
  mechanism.

## 12. Worked examples

[`prototype/`](../../../.scratch/mastering-policy-language/prototype/) —
throwaway, marked as such. `policy-person.json` (C-J, Tiers A–D, one
activation entry) and `policy-company.json` (CIK, Adjudicated Seed Links,
deterministic crosswalk, no activation) read by `interpret.mjs` reproduce
research 18 **to the row**: person 841/841, entity 353/353, 26 deferred
over the 1,220-row labelled sample; 1.2% deferral over the whole corpus.
`interpret-binding.mjs` runs Tier A binding with a real identity store
over 72,981 decisions. `demo.html` opens by double-click with six guided
cases. Survivorship was **not** exercised — it needs a populated identity
store.

## 13. Dependencies on Clean MDM and items raised for Codex

This is a proposal against `mdm_v2.policy`, `clean/merge.py`,
`clean/store.py` and `clean/adapters.py`, all Codex/Grok's. Items they must
decide, in the order they bite:

1. ~~**Composite-digest provenance churn.**~~ **Resolved 2026-09-23** (PRs
   #695, #696). The whole-body digest was stamped on every selected field and
   folded into `business_hash`, so a Person-only edit changed Company field
   provenance on the next Company batch. A field now records its kind's own
   digest with the kind version beside it, narrowed to the authority-bearing
   sections (§8); a profile field records its role's digest. Release gate 14.4
   is met.
2. **Q11's confidence coverage.** Accepted Q11 says one-sided **95%**;
   research 18 measured one-sided **97.5%** (n ≥ 268 vs ≥ 381 at a 99%
   bar; 2,703 vs 3,838 at 99.9%). Proofs at different coverage are not
   comparable, hence the single `one_sided_confidence` field required
   equal in bar and proof. Codex settles which Q11 means.
3. **Two accepted rules with no implementation**: coherent field groups
   (`merge-stage.md:137-139`) and the publication-time tiebreak
   (`merge-stage.md:129`); `survivorship.py:239-249` skips both.
4. **Q16 amendment.** `automatic_rules` non-empty is today a refusal; this
   document asks that it be accepted when every entry passes §9 — the
   proof replaces the prohibition, it does not weaken it.
5. **Person Q11 at 99%** — the earlier proposal
   ([handover](../../../.scratch/handover/2026-09-20-claude-to-codex-person-q11-amendment.md))
   this document's Person bar depends on.
6. **Q11 speaks of precision only.** The `deterministic` activation kind
   (§9.3) is an addition to accepted policy, with its evidence.

## 14. Release gates

1. Registration refuses all eight checks in §10 on a fixture set that
   includes the prototype's six abuse cases.
2. `interpret` over the accepted Person and Company documents reproduces
   research 18 to the row and research 07's binding run to the decision.
3. Every automatic verdict live in production has a proof in the body
   whose sample files re-score in CI to the stated `n`/`correct`.
4. ~~A Person-only edit does not change Company field provenance (item 13.1
   resolved one way or the other, recorded).~~ **Met 2026-09-23**: item 13.1
   resolved and recorded; asserted directly in
   `tests/mdm/test_clean_survivorship.py`.
5. The deterministic tolerance has tripped at least once on an injected
   fault in a non-production run, and never on the production cohort,
   before any deterministic rule runs alone.
6. ~~`CONTEXT.md` carries **Mastering Policy** and **Identifier Contract**.~~
   **Met**: `CONTEXT.md:65` and `:69`.

## 15. Open

1. **Re-projection scope on re-registration** (§11).
2. ~~**Home of classification rule text**~~ — **settled 2026-09-23** (§4.3):
   the kind document's `rules` list, named from the dataset contract's adapter
   block, resolved at read time. Still open with it, the
   **field-alias map** (document field path → source column) that the
   prototype had to hard-code: it is the dataset contract's adapter block
   and nothing has yet specified it.
3. **Authoring surface** — repo files registered by `store.register_policy`
   is the assumed default; how the composition is built and validated
   before registration is not specified.
4. **Person projection** — the field set, privacy classification and
   retention wait on the Person map's ticket 04.
5. **Migration of rules already written** — restated in policy documents
   (the prototype's approach) or referenced from their tickets.

## 16. Evidence

| Decision | Ticket | Evidence |
| --- | --- | --- |
| Destination, boundary, families | map Q1–Q3 | grilled 2026-09-20 |
| One document per kind, composed | [01](../../../.scratch/mastering-policy-language/issues/01-research-policy-document-granularity.md) | research 01 |
| Activation per verdict, proof beside the rule | [02](../../../.scratch/mastering-policy-language/issues/02-research-rule-activation-and-proof.md) | research 02 |
| Twelve primitives, versioning | [03](../../../.scratch/mastering-policy-language/issues/03-define-primitive-vocabulary.md) | research 03 |
| The language holds; four findings | [04](../../../.scratch/mastering-policy-language/issues/04-prototype-person-and-company-documents.md) | prototype |
| Deterministic activation, defer and count | [06](../../../.scratch/mastering-policy-language/issues/06-decide-how-a-deterministic-rule-activates.md) | research 07 |
| Rule C-J | Person [03](../../../.scratch/person-consumer-contract/issues/03-decide-reporting-owner-classification.md) | research 18 |
| Tiers A–D | Person [02](../../../.scratch/person-consumer-contract/issues/02-decide-what-binds-a-person.md) | research 15, 16 |
