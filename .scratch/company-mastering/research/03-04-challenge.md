# Challenge pass on tickets 03 and 04

Type: research
Date: 2026-09-23
Branch: `claude/company-mastering-policy-runtime`
Subjects: `.scratch/company-mastering/issues/03-implement-classification-and-binding-predicates.md`,
`.scratch/company-mastering/issues/04-prove-identifier-only-company-binding.md`

## What I checked

Every `file:line` either ticket names, opened on this branch. The whole of
`edgar_warehouse/mdm/clean/` — the two new modules (`classification.py`,
`primitives.py`) line by line, plus `merge.py`, `store.py`, `evidence.py`,
`adapters.py`, `cli.py`, `assessment.py`, `identity.py`, `survivorship.py`,
`native_consumption.py`, `company_source.py`, `gleif_source.py`. Migrations
`023`, `028` and `030` where the tickets cite them, and `store.CLEAN_MDM_MIGRATIONS`.
The accepted specs (`docs/specs/clean-mdm/company-policy.md`,
`company-completion.md`, `docs/specs/mdm/policy-language.md`) and the committed
prototype (`interpret.mjs`, `policy-person.json`, `policy-company.json`),
which I parsed rather than read, so the rule/step/argument counts below are
machine-derived. The two build commits `5017014b` and `db8e4a86` and their
messages. `.scratch/company-mastering/research/01-02-challenge.md` first, as
instructed — F5, F6 and F7 in particular, so that findings here are the new
consequence rather than the settled gap restated.

## What I could not check

- **Nothing was executed.** No database, no migration run, no test run, no
  `node run-check.mjs`. Every claim is a claim about source text. In
  particular I did not run the prototype to confirm it still reproduces
  research 18, and I did not run the Python evaluator against
  `policy-person.json` — the refusal below is read off the two guard clauses,
  not observed.
- **Whether the operator intends decision 3's "same bar" to cover measured
  rules at all.** The decision does not distinguish; I argue both sides in F3
  and reach a verdict, but the intent is the operator's.
- **The Wilson arithmetic.** Re-derived in the 01-02 pass; unchanged here and
  not repeated.

## Verdict table

Four decisions from ticket 03, five claims from ticket 04, two implementation
judgement calls.

| # | The decision, in short | Verdict |
|---|---|---|
| 03-D1 | Merge Stage is the system of record; the lookup happens inside its transaction | **unsound** — the stated concurrency guarantee does not follow from that boundary (F2) |
| 03-D2 | One record = one entity of one kind; each entity resolves on its own | **sound** — the shape is real; the Form 4 illustration is not (F7) |
| 03-D3 | A new entity seen many times in one run gets one id, matched on the same rule and bar | **unsound** — the bar does not transfer, and the id depends on partitioning (F3) |
| 03-D4 | Classification runs at read time, because the kind is hashed into `assertion_id` | **sound** — the hash argument is exact; it is silent on *which* policy and records no rule (F1, F4) |
| 04-C1 | Declare namespace, authority, normalization/primitive versions, scope+cardinality, compatibility in the pinned policy | **unsound** — faithful to `company-policy.md`, but omits `tolerance`, so a contract built to this list cannot pass §9.3 activation (F5) |
| 04-C2 | Verify the contract to activate; verification, not a statistical gate | **sound** |
| 04-C3 | Missing, ambiguous, conflicting, suspended or unsupported-namespace **defers**; never binds | **unsound** — "defers" is not what the spec says, and would defer nearly every record (F5) |
| 04-C4 | An LEI never establishes a CIK crosswalk merely because both values exist | **sound** — and already structurally enforced |
| 04-C5 | A name change or lapsed registration alone never revokes a binding (Q9) | **sound** — trivially so today; Q9's other half is unbuilt |
| JC-1 | `token_match` with neither count is refused, where the prototype returns true | **sound** — verified independently against both documents |
| JC-2 | A catch-all must be `otherwise: true`; an empty `when` does not count | **sound** — and spec-mandated, not a divergence (F6) |

**Count: 7 sound, 4 unsound, 0 unverifiable.**

The empty "unverifiable" bucket is again a real result rather than a courtesy.
Every claim in both tickets names either a code site, a spec line or a
prototype document, and all of them exist and are readable on this branch.

The four failures are not evenly distributed. Two of them (03-D1, 03-D3) are
the two halves of the same unbuilt thing — how a record finds or mints an
entity id — and they fail for a related reason: nothing the Merge Stage
currently compares would notice a concurrent or cross-batch mint of the same
entity. The other two are ticket 04's, and both are about the *completeness* of
a requirements list rather than a wrong idea: C1 omits an element §9.3 requires,
C3 hardens a permissive spec sentence into a blocking runtime behaviour.

The two most serious *findings* (F1, F4) are not attached to an unsound row.
They are defects in the code that decision 4 requires, and decision 4 itself is
correct. The 01-02 pass set that precedent with F5 against a sound 02-Q2.

---

## Findings, most serious first

### F1 — Nothing pins a rule body to its `(rule_id, version)`, and the assertion records no evidence of which rule decided its kind. The pinning hole the brief suspected is real and reachable.

**What the code does.** `resolve_rule` matches on id, then insists on the
version, inside one kind's `rules` list.

`edgar_warehouse/mdm/clean/classification.py:54-62`:
```python
block = (policy.get("kinds") or {}).get(named["kind"]) or {}
for rule in block.get("rules") or []:
    if rule.get("rule_id") == named["rule_id"]:
        if rule.get("version") != named["version"]:
            raise Conflict(...)
        return rule
```

**Nothing forces the pair to carry one body.** `register_policy`
(`store.py:167-190`) performs exactly two checks — the `automatic_rules`
refusal (`:169-170`) and the `kinds`/`fields` ambiguity (`:174-175`) — then
digests the body and inserts it (`:183-189`). It never walks `kinds`, never
looks at a rule, and never compares a rule against anything previously
registered. **None of `policy-language.md:400-418`'s eight registration checks
exist**, including item 1 (every primitive is a registered `name@version`) and
item 2 (exactly one `otherwise` step) — both of which `classify` now performs
per record instead, at a different moment and with a different blast radius.

So the brief's scenario is reachable exactly as stated: register policy A
holding `C-J@2026-09-20` with steps S1, register policy B holding
`C-J@2026-09-20` with steps S2. Both succeed. Both digests are valid. A
Dataset Contract naming `C-J@2026-09-20` classifies the same record
differently depending on which body the read loaded, and `resolve_rule` is
satisfied in both cases because the version string matched.

**The spec states the invariant and assigns it to nobody.**
`policy-language.md:428-430`: "Any edit mints a new digest. A rule edit changes
`rule.version` and orphans its activation entry". That is a discipline on the
author, with no enforcement anywhere in `clean/`. Ticket 01's "pointing at a
different rule version is a mapping change" (restated at
`classification.py:48-50`) does **not** cover this: it governs the contract's
*pointer*, not the rule's *body*. A body edit under an unchanged version moves
no pointer, so no mapping version is minted and no second row is written.

**The assertion carries no evidence either.** `evidence.assertion`
(`evidence.py:80-104`) hashes `kind` into the body and nothing else about how
the kind was decided — no rule id, no version, no step, no policy digest.
`policy-language.md:210-213` requires precisely that: "Source category,
asserted legal form and inferred kind are stored **separately** with the rule
id, version and step that fired". So the assertion is not replayable to its
own classification: given a row, there is no way to say which rule produced
`kind`, and therefore no way to detect after the fact that two bodies disagreed.

**The failure this produces.** Two records of the same real company, read a
month apart under two policy digests that both hold `C-J@2026-09-20`, get
different kinds. They land in different `KINDS` buckets; `merge.py:392-396`
raises `kind_conflict` on the entity they should share, or — worse, and more
likely — they are never proposed for the same entity at all, because a
`person` and a `company` subject are not candidates for one another. Nothing
in the run reports why, because neither assertion says which rule ran.

**What would have to change.** One of:

1. `register_policy` refuses a body whose `(kind, rule_id, version)` triple
   already exists in `mdm_v2.policy` with a different rule body. This is a
   bounded scan over registered policies and matches the spirit of
   `store.protected_change` (`:320-340`) — the engine compares the parts
   itself rather than trusting a label.
2. The assertion records the rule that fired, hashed with the rest of the body
   the way `mapping_version` was (`evidence.py:64-68`, `:102-103` — the same
   file already holds the precedent, including the "absent means the first
   reading" canonicalisation trick).

**Do not reach for the per-kind digest for (2).** `survivorship.py:265-274`
puts `"rules"` in `NON_AUTHORITY_SECTIONS` by name, with a comment saying why
("classification and binding: they decide a kind or an identity"), and
`_kind_authority` (`:306-345`) digests only `AUTHORITY_SECTIONS =
("fields", "field_group", "field_groups")`. Ticket 02's amendment deliberately
excluded rules from that digest to stop classification edits churning field
provenance. Stamping it on the assertion would therefore record a digest that
is *guaranteed not to move* when the rule changes — the exact opposite of what
is needed. This needs its own rules digest, or the literal
`(rule_id, version, step)` triple.

### F2 — 03-D1: the concurrency guarantee does not hold, because the assessment scope is keyed on subjects and a candidate key is not in it.

**What the decision says.** "The lookup and the write are never separated, so
two concurrent runs reading the same new entity cannot both miss and both
mint: one wins and the other sees the first one's id."
(`03-...md:31-38`).

**What the repo says.** Run the decision's own scenario through the code and
both runs mint. The apply path is two transactions, and only the second one
commits.

`merge.py:127-138`:
```python
for attempt in range(3):
    prepared = self.assess(**command)
    ...
    return self.apply_assessment(prepared["assessment_id"], run_id=command["run_id"])
```

`assess` computes the proposal by running `_execute(preview=True)`
(`merge.py:166`), which takes the advisory lock (`:286`), does its work, and
then **rolls back** (`:601`). `apply_assessment` re-executes the *retained*
command (`:193-199`) — it does not recompute it.

**Trace the two runs the decision is about.** Two runs read two *different*
source records that should resolve to one new entity.

- Both call `assess`. `pg_advisory_xact_lock(730234)` (`:286`) serialises them,
  but the first rolls back at `:601`, so the second sees an unchanged store and
  mints its own id.
- Both apply. `assessment.check` (`assessment.py:40-49`) and
  `028:160-162` compare `assessment_snapshot` — but that snapshot is scoped
  to `scope["keys"]`, built at `merge.py:311-319` from the assertions'
  **subjects** and the decisions' anchors. Two different records have two
  different subjects (`evidence.subject_key`, `:34-35`), so neither run's
  commit changes the other's snapshot.
- `merge.py:353-355` refuses only a *duplicate* `entity_id`
  ("Identity allocation already exists"). Two distinct fresh UUIDs are not a
  duplicate.

Both commit. Two entity ids exist for one real entity — precisely the
"duplicate ids to be consolidated afterwards" outcome the decision says it
rejects, and it lands in Q10/Q11 territory, which the decision itself calls
"a separate, harder problem".

The guarantee *does* hold in one narrower case: two runs reading the **same**
subject. There the second run's snapshot changes, `check` raises
`StaleAssessment`, `apply` retries (`:136-138`), and the re-assessment sees the
committed id. The decision's wording — "reading the same new entity" — reads
as the general case but is only true of the same *record*.

**Also worth noting, and separate:** nothing in `clean/` mints an entity id at
all today. `mdm_v2.identity` has no default (`023_clean_mdm.sql:53-58`,
`entity_id uuid PRIMARY KEY`), and `commit_batch_evidence` inserts what it is
given (`023:170-173`). Ids arrive pre-minted in the manifest
(`cli.py:290`, `batch.get("identities", [])`). So today candidate resolution
happens entirely outside the transaction, in whoever authors the manifest —
which is the rejected alternative, running in production now.

**What would have to change.** The guarantee needs the *candidate key* — the
thing a lookup would match on — to be inside the assessment scope, so that a
concurrent mint of a matching entity invalidates the proposal instead of being
invisible to it. Today `scope["keys"]` holds subjects, entity ids and decision
anchors (`merge.py:311-319`) and nothing that says "this record is looking for
a company with CIK 320193".

**What constrains the fix, and why it is not free.** The minted ids must be in
the command *before* the applying transaction, because the SQL refuses any
drift between assessed and applied:

`028_clean_mdm_assessment.sql:157-159`:
```sql
IF (r - 'assessment_id' - 'expected_generation') IS DISTINCT FROM b->'effects' THEN
    RAISE EXCEPTION 'Command differs from assessed effects';
```

So a lookup that *changed* the command inside `apply_assessment` is rejected
outright, and a lookup that mints inside `assess` has its writes rolled back at
`merge.py:601`. That does not make decision 1 and Q13 incompatible — widening
the scope preserves both, and `apply`'s retry loop (`:127-138`) is already the
mechanism that turns an invalidated proposal into a re-assessment against the
winner's committed id. It does mean the fix is a change to what
`assessment_snapshot` reads (`028:28-74`), not a change to where the lookup
sits, and decision 1's phrasing — "the lookup and the write are never
separated" — describes an arrangement the current two-transaction shape does
not offer. Say what it is instead: *the proposal is invalidated by anything
that would have changed its answer.*

### F3 — 03-D3: a measured bar cannot transfer to a within-run match, and the minted id depends on how the run was partitioned.

**What the decision says.** "the run must match the record against *the pending
entities of the same run* … That match is made on evidence not yet committed,
so the rule that makes it must be **the same rule** used against master data,
held to the same bar — not a looser within-batch shortcut." (`03-...md:49-61`).

**On the bar — argued both ways, then a verdict.**

*For transfer.* A bar is a property of the rule, not of the store it reads.
`policy-language.md:362-364` describes a §9.3 deterministic rule as one "whose
`when` is identifier primitives only", with "no precision to measure" — its
failure mode is a wrong contract, not a wrong score. An exact CIK match against
a pending entity is the same test as against a committed one, and §7.2's
`compatibility` comparison works against a pending record's own name as well as
a stored one. For deterministic rules, transfer is fine.

*Against transfer.* `policy-language.md:328-336` makes the measured bar a
Wilson lower bound over a labelled cohort — for C-J, "n: 841, correct: 841"
drawn from bronze filing artifacts. That measurement was taken on records
compared against *committed master data*, with whatever corroborating fields a
committed entity carries. A pending entity has strictly less: no accumulated
identifiers from other sources, no survivorship-selected fields, no prior
bindings. It is a different population with a different error rate, and the
841/841 says nothing about it. Worse, the errors correlate: if a rule
mis-matches record 40 to pending record 1, both land on one id and the error is
not independently sampled at all.

**Verdict: coherent for §9.3 deterministic rules, incoherent for §9.2 measured
ones, and the decision does not distinguish.** This is the same shape of error
ticket 02's suspension line made and was amended for — "the line is scoped
where the spec puts it … firing only on §9.3 deterministic verdicts"
(`02-...md:116-122`, recorded at `map.md:83-87`). The fix shape is therefore
already accepted rather than open-ended: scope the within-run match to
deterministic rules, and defer a measured within-run candidate.

**On ordering — a deterministic sort does not remove the dependence.**
`merge.py:226` sorts assertions by `assertion_id`, which is a hash of the body
(`evidence.py:104`). That fixes the order *within one batch's input set*. It
does not fix which records are in that set, and three things vary it:

- `merge.py:231-236` refuses a batch over 1,000 assertions-plus-deferred, so a
  large run is necessarily many batches;
- each `_execute` is its own transaction (`merge.py:285`), so batch N's mints
  are committed before batch N+1 reads;
- `execute_manifest` walks batches against a `--limit` budget and **breaks
  mid-manifest** (`cli.py:277-280`), leaving the rest for a later invocation.

So "the run's own pending entities" collapses, across a batch boundary, into
"master data as of the previous batch". Partition the same 2,000 records as
2×1,000 versus 4×500 and record 1,200 may be matched against a committed
entity in one partitioning and against a pending one in the other — and if the
within-run rule and the master-data rule ever behave differently, or if the
within-run match is scoped to deterministic rules per the verdict above, the
resulting ids differ.

Set that against the map's verification bar: "Prove reordered and duplicate
input, … and stable surviving IDs" (`map.md:43-48`). Whether that bar is about
*id assignment* or about the *final entity set* is the operator's call, and the
two are not the same claim. If it means id assignment, decision 3 as written
cannot satisfy it without pinning the partitioning; if it means the entity set,
it can, and the ids are simply not reproducible across repartitioning — which
should then be written down, because "a stable surviving ID" reads as the
stronger claim.

**On retry — no ids are minted, so nothing is re-minted.** `apply` retries up
to three times on `StaleAssessment` (`merge.py:127-138`), and each retry calls
`assess` afresh on the *same* `command`, whose `identities` came from the
caller (`cli.py:290`). No `uuid4()` exists anywhere in `clean/` — the only
`uuid4()` calls in `edgar_warehouse/mdm/` are in the legacy pipeline
(`pipeline.py:1032`, `universe.py:76`) and `gen_random_uuid()` defaults are on
legacy tables (`001_initial_schema.sql:26`), not `mdm_v2.identity`
(`023:53-58`). So retry is deterministic today by virtue of allocating nothing.
The moment decision 3 is built, this becomes a live question, and the answer
must be a deterministic derivation (a digest of the matched evidence, the way
`subject_key` is derived) rather than a random UUID — otherwise a rolled-back
first attempt and its retry mint different ids for the same entity and the
`028:157` byte-equality check turns every retry into a hard failure.

### F4 — Decision 4 puts classification at read time; there is no read-time policy path at all, and the two new modules have no caller.

**What the decision says.** Recorded in `db8e4a86`'s message and at
`classification.py:9-11`: "The policy is therefore resolved at read time,
beside the contract (operator decision, 2026-09-23)."

**What the repo says.** `classify` and `resolve_rule` are called from exactly
one place, and it is a test:

```
$ grep -rn "resolve_rule\|classify(" --include=*.py edgar_warehouse/ tests/
edgar_warehouse/mdm/clean/classification.py:40:def resolve_rule(...)
edgar_warehouse/mdm/clean/classification.py:68:def classify(...)
tests/mdm/test_clean_classification.py:14:from ... import classify, resolve_rule
```

The read path still decides the kind from the contract's lookup table:
`adapters.py:77-84` reads `mapping["kind_field"]` and
`mapping["kind_values"].get(source_kind)`. `normalize`'s signature
(`adapters.py:60-66`) takes `row, source_code, contract, publication,
mapping_version` — no policy, no connection. Its GLEIF twin
`gleif_source.record_evidence` (`:437-447`) takes the same shape.

**Is the batch's `policy_digest` available at read time?** In the manifest,
yes — `read_manifest` returns the parsed manifest (`cli.py:49-64`) and
`execute_manifest` reads `manifest["policy_digest"]` at `cli.py:284`. The
fixture confirms the field is top-level and required in practice:
`tests/fixtures/clean_mdm/v1/manifest.json` has keys
`['as_of', 'batches', 'contract_version', 'policy_digest']`. But
`batch_evidence(batch, root, store)` (`cli.py:100-102`) is called at
`cli.py:266` with three arguments and opens its own connection for
`current_reading` alone (`:118-124`). The native path is the same:
`prepare_native(manifest, store, coordinator, verifier, observed, limit)`
(`native_consumption.py:16`) has the whole manifest in hand and never reads
`policy_digest` from it.

**So "what stops a record being read under policy A and committed in a batch
pinned to policy B" is: nothing, and also nothing yet reads under any policy.**
There is no check because there is no second thing to check against. The
observable damage, once the wiring lands without a pin, is F1's failure with a
shorter fuse: the kind is hashed into `assertion_id` (`evidence.py:104`), so a
read under the wrong policy produces a *different assertion id* for the same
record, which then sits beside its sibling as a second row and trips
`survivorship.py`'s contradictory-publication guard — the same mechanism the
01-02 pass documented as F1 for mapping versions.

**The `preview`/assessment path is safe, and that is worth saying explicitly**
(see F8's one-liner for why it composes): the retained command carries
`policy_digest` (`merge.py:153` copies everything but `run_id`/`preview`),
`028:91` enforces `effects.policy_digest == command.policy_digest` at
recording time, and `028:157` enforces byte-equality of the whole command at
apply time. A retained assessment therefore cannot be applied under a different
current policy. `assessment_snapshot` (`028:28-74`) does not scan
`mdm_v2.policy` — it does not need to, *because* of the command-equality check.
If anyone ever relaxes `028:157`, policy drift becomes invisible.

**Not new, and framed as such.** The 01-02 pass's F5 already found that 02-Q2
"answers where classification sits but not how it reaches `normalize`", and
`map.md:104-105` carries "How the classification rule reaches the code that
uses it" as unspecified fog. What is new is that the resolver now exists, is
tested, and is unreachable — so the gap has moved from "undesigned" to "built
and unwired", and the cheapest moment to decide which policy a read uses is
before the first caller exists.

### F5 — 04-C3 hardens a permissive spec sentence into a blocking behaviour, and "suspended" names a state the design cannot currently hold.

**What the ticket says.** "an identifier that is missing, ambiguous,
conflicting, suspended or of an unsupported namespace **defers**; it never
binds" (`04-...md:18-19`).

**What the spec says.** `company-policy.md:85-87`:

> An identifier match must resolve to one compatible Company. Missing,
> ambiguous, conflicting, suspended or unsupported identifier evidence does not
> gain binding authority.

"Does not gain binding authority" and "defers" are different outcomes. A record
with no CIK does not gain binding authority — the rule simply does not fire, and
the record is left for another rule or for the ordinary `binding_required`
review `merge.py:446-454` already emits. Deferring it is a stronger act: in
this codebase a deferral is a durable `mdm_v2.deferred_record` row with a
blocking review projection (`merge.py:503-521`, `030:30-39`), and blocking
disposition feeds the completion gate.

**The concrete failure.** Applied literally to "missing", C-J-classified GLEIF
records — most of which have no SEC CIK — would each produce a blocking
deferral against the CIK rule. `company-completion.md` requires deferral counts
to make the boundary checkable; a run that defers every record for lacking one
of two identifiers reports a boundary that means nothing, and
`company-policy.md:59` ("A run that merely defers everything") is the state the
gate is written to catch.

The spec's *only* use of "defer" in this area is narrower still:
`policy-language.md:380` — "**Defer** the violating record to the Steward; the
rule keeps running" — which is §9.3's response to a *claim violation*, i.e. a
materially-new name on an identifier that already resolves. That is the
"conflicting" case alone, not all five.

**"Suspended" has no representable state.** Ticket 02 decision 5 put suspension
in its own table and, amended, keyed the row
`(policy_digest, kind, family, rule_id, rule_version)` (`02-...md:110-113`,
restated in its build list at `02-...md:155-158`). The same decision then says
the line is "scoped where the spec puts it: per `(kind, namespace)` Identifier
Contract" and warns, in its own words, that "A rule may name several
namespaces, each with its own tolerance … so one counter per rule would
silently collapse distinct measured lines into one" (`02-...md:116-125`).

The stated key contains no `namespace`. One row per
`(policy_digest, kind, family, rule_id, rule_version)` is exactly one counter
per rule — the collapse the same paragraph forbids. Either the key gains
`namespace`, or the row's body holds a per-namespace map and the build list
should say so. Ticket 04 inherits this: it is the ticket that must make
"suspended" mean something, and the table it would read cannot currently
distinguish a suspended `sec.cik` from a suspended `gleif.lei` on the same rule.

**04-C1's omission is the same soft spot from the other side.** The ticket's
declaration list (`04-...md:13-16`) tracks `company-policy.md:78-80` closely and
faithfully. But `policy-language.md:367-371` is what a §9.3 activation
predicate actually checks:

> the predicate checks instead that every namespace the rule names has a
> contract (§7.2) with `claim.forward`, `compatibility` (predicate, version,
> **field**), `verification` with a corpus hash, and a complete `tolerance`
> block, and that every named primitive resolves.

`tolerance` appears in neither ticket 04's list nor `company-policy.md:78-80`.
That checklist is closed: a contract built to the ticket's list is missing the
one element §9.3 names as required-and-complete, so the rule it governs cannot
activate, which is the whole point of the ticket ("verify the contract to
activate the rule"). It is also the element carrying the open design question
(`map.md:94-99`, "no runtime kill switch") and the key problem above. That is
why C1 is marked unsound rather than sound-with-a-note: nothing in it is
*wrong*, but a build that satisfies it does not produce a rule that runs.

### F6 — JC-2 is spec-mandated, not a divergence, and the committed prototype document was already stale against its own spec.

**The prototype's C-J really does end with an empty `when`.** Parsed from
`.scratch/mastering-policy-language/prototype/policy-person.json`, rule `C-J`
version `2026-09-20`, final step:

```json
{ "step": "4", "verdict": "deferred", "note": "Everything else — Steward.", "when": [] }
```

No `otherwise` key. So the Python refuses it twice over —
`classification.py:76-79` raises "has no catch-all step" before evaluating any
record, and `:88-94` would raise on the empty `when` if it ever got there.
**`policy-person.json` would not load under the new evaluator.**

**But the spec already said so, and its own listing of C-J already complies.**
`policy-language.md:205-207`:

> The catch-all is written `"otherwise": true`, never an empty `when`
> (prototype finding 3; an empty list reads as "always true" and is easy to
> mis-edit by hand). A rule without a catch-all is refused.

`policy-language.md:406-407` makes it a registration check: "Every
classification rule has exactly one `otherwise` step and every step names a
verdict in `emits`." And §6's own canonical C-J listing at
`policy-language.md:195` shows `{ "step": "4", "verdict": "deferred",
"otherwise": true }`. The spec and the committed JSON have disagreed since the
spec was written; the Python simply enforces the spec's side.

**Does it matter?** No, operationally. The prototype is evidence, not a
fixture: `policy-language.md:438-450` (§12) cites it as a worked example, and
the only things that load it are other prototype files
(`run-check.mjs`, `demo.html`, `build-demo.mjs`, `research/07-run-binding.mjs`)
plus a docstring mention in `tests/mdm/test_clean_primitives.py:9-10`. Nothing
under `tests/` or `edgar_warehouse/` parses it. The measured run it stands for
was produced by `interpret.mjs`, which is unchanged.

**Two narrow divergences from the spec worth a line each**, both in
`classification.py:76-79`: the Python requires **at least one** `otherwise`
step where `policy-language.md:406` says **exactly one**, and it does not
require the `otherwise` step to be last — a rule with `otherwise: true` at step
0 would return that verdict for every record and never reach the rest. Both are
registration-check territory (§10) that has not been built (F1), so they are
currently the only place such a body would be caught at all.

### F7 — 03-D2's shape claim holds; its Form 4 illustration has no adapter, and ticket 04 has no primitives.

**The shape is real.** `adapters.normalize` returns exactly one `assertion(...)`
per row (`adapters.py:166-183`), the kind is decided per record from
`kind_field`/`kind_values` (`:77-84`), and relationships are carried on the
assertion as `target_subject` pointers (`:135-149`) resolved later against
`state.bindings` (`merge.py:465`). `gleif_source.record_evidence` returns one
`(kind, body)` tuple per row (`:437-447`). So "one source record describes one
entity of one kind" is precisely what the code does, and the ticket is right
that it was worth writing down.

**The Form 4 illustration is not.** "A Form 4 produces two records — the issuer
as a Company, the reporting owner as a Person — plus the relationship between
them" (`03-...md:40-46`). There is no ownership adapter in Clean MDM. The only
`SOURCE_CODE` in the package is `company_source.py:23`,
`"sec.submissions.company.v1"`, whose `kind_values` maps exactly one entry,
`{"operating": "company"}` (`:49`); the other registered source is native
GLEIF. `grep -rn "ownership\|reporting_owner\|form4" edgar_warehouse/mdm/clean/`
returns only two unrelated hits about schema ownership. So "This is already
what `adapters.normalize` and the assertion shape do" is half-true and should
be split: the shape is already right, the example describes an adapter nobody
has scoped. Two records from one filing also implies the *source file* carries
two rows, which is a contract-authoring decision (`record_key`,
`kind_field`) that no ticket currently owns.

**And ticket 04 has nothing to build on.** `primitives.REGISTRY`
(`primitives.py:169-177`) holds five entries, all `family="classification"`.
`identifier_match@1` and `identifier_cardinality@1` — the two primitives
`policy-language.md:238-241` shows a Tier-A binding rule calling, and the two
ticket 04's Identifier Contract exists to govern — are not in it. Ticket 04 is
"Blocked by: 03" (`04-...md:5`), and ticket 03's "Still to build"
(`03-...md:92-97`) names "the binding predicates", so the sequencing is
consistent; it is worth stating plainly that ticket 04's implementation surface
today is zero, because C1-C5 read as though they are checks against something.

### F8 — Primitive parity against the prototype: one real divergence, no consumer; plus three small asymmetries.

I compared each of the five implemented primitives against `interpret.mjs`.

**`_tokens_found` (`primitives.py:95-111`) reproduces `tokensFound`
(`interpret.mjs:37-49`) exactly**, including both details the brief flags. The
`AND` skip is the same (`primitives.py:104-105` / `interpret.mjs:42`), and the
synthetic `&` token uses the same two-part test — raw contains `&` **and** the
padded normalized text contains `" AND "` (`primitives.py:109-110` /
`interpret.mjs:47`). `_conformed` (`:65-70`) matches the JS normalizer
character for character, including `&` → `" AND "` before punctuation
stripping. Note for the record: `policy-person.json`'s `entity_legal_form` list
(125 entries) does **not** contain `"AND"`, so the skip never fires on the
proven document and the `&` token is purely synthetic in both.

**`_name_shape` (`:141-159`) reproduces `name_shape@1`
(`interpret.mjs:70-81`) exactly**: `forbid_characters` and `forbid_digits` read
the raw string before normalizing (`:147-150`), tokenization splits the
normalized string on `[\s,]+` (`:151-153`), the bounds check is the same
inclusive range, the "at least two non-suffix tokens" rule is the same
(`:156-158`), and the final `[A-Z]+` check is `re.fullmatch` against JS's
`/^[A-Z]+$/` (`:159`).

**`is_empty` (`:51-52`) is the one real divergence.** Python's `item == 0` is
true for `False`, because `False == 0` in Python; JS's `v === 0` is not true
for `false`. So a boolean-`False` field is "empty" to the Python and "present"
to the JS. **No consumer reaches it**: `policy-person.json`'s
`structural_fields` are six SEC submissions paths (`sec.submissions.sic`,
`stateOfIncorporation`, `ein`, `tickers`, `ownerOrg`, `fiscalYearEnd`), all
text or array. On the brief's fiscal-year-end question specifically: the one
registered Company contract declares `"field_shape": "nullable_text"`
(`company_source.py:45`), so `fiscal_year_end` is the string `"1231"` and
`"0" == 0` is `False` in Python — the concern does not bite on any contract
that exists. It would bite the moment a numeric-typed source declares a
legitimately-zero field, and `is_empty`'s treatment of `0` is inherited from
the prototype rather than decided, so it is worth deciding once.

Three smaller asymmetries, all Python-stricter and all fine:

- `declared()` (`:55-62`) refuses an undeclared list by name; the JS
  substitutes `[]` (`interpret.mjs:57-58`, `78`, `84`), which silently makes
  `token_match` find nothing and `fields_all_empty` vacuously true.
- `field_in_set` uses Python `in` (`:119`), i.e. `==`, where JS `includes` uses
  SameValueZero. `True in [1]` is true in Python and `[1].includes(true)` is
  false in JS. No document reaches it.
- `classify` (`:80-97`) validates a step's `verdict` against `emits` only for
  steps it *reaches*, returning at the first match (`:96`). A bad verdict in a
  later step passes unnoticed whenever an earlier step fires. `§10` item 2 puts
  this check at registration, where it would cover every step; see F1.

### F9 — Ticket 03 and the map have both been overtaken, and ticket 04 is blocked on more of ticket 03 than ticket 03 lists.

- **`03-...md:9`** — "Nothing to decide once 01 and 02 land." Four decisions
  later this is plainly false, and the ticket's own heading at `:28` says
  "surfaced three" while the section carries a fourth as decision 4 in the
  brief. In the ticket file itself, decision 4 (classification at read time)
  **is not present at all** — it exists only in `db8e4a86`'s commit message and
  `classification.py:9-11`. The most consequential of the four is the one not
  written on the ticket.
- **`03-...md:96`** — "Still to build: … classification per source record".
  `classification.py` exists and is tested; what is missing is its caller
  (F4). The line should say so, because "not built" and "built and unwired"
  need different next actions.
- **`03-...md:13`** — `store.py:162` is wrong. Line 162 is
  `"checksum": checksum,` inside `migrate`'s return dict; the refusal is
  `store.py:169-170`. `map.md:33` repeats the same stale pointer, and the spec
  cites the same refusal as `clean/store.py:155-156` twice
  (`policy-language.md:169-170`, `:356-357`) — `store.py:155` is inside
  `migrate`'s leaked-privilege query. The spec's companion pointer
  `merge.py:183-184` is wrong the same way: those lines are inside `assess`'s
  exception handler, not the policy check at `:303-304`. Three documents, one
  refusal, four wrong line numbers.
- **`map.md:26-28`** — "migrations 028-030". `store.CLEAN_MDM_MIGRATIONS`
  (`:43-52`) now runs through `032`, both of which this ticket added.
- **`map.md:33-36`** — "The runtime refuses every automatic rule … That
  refusal is the safety net; it comes out only with its replacement in place."
  Still true and still verified (`store.py:169-170`, `merge.py:303-304`), which
  is worth saying because it is the reason none of the above is currently
  live.
- **`04-...md:5`** — "Blocked by: 03" is right but understates the debt.
  Ticket 03's "Still to build" (`03-...md:92-97`) names "the binding
  predicates", "the activation bar per `(kind, family)`" and "the suspension
  table", and ticket 04 needs all three *plus* things neither ticket
  enumerates: the two identifier primitives absent from `primitives.py:169-177`,
  an Identifier Contract resolver over `kinds.<kind>.identifiers`
  (`policy-language.md:257`), a per-`(kind, namespace)` tolerance reader, and
  the §9.3 deterministic activation predicate itself
  (`policy-language.md:367-371`). Ticket 04's implementation surface today is
  zero, and scheduling it needs that list, not "blocked by 03".
- **`map.md:104-105`** — "How the classification rule reaches the code that
  uses it" is still listed under "Not yet specified", and it still is. Decision
  4 answered *when* (read time) and not *which policy* or *through which
  signature*. The fog entry is accurate; it should now name the built-and-
  unwired resolver so the next session does not re-derive it.

---

## Citation audit

Every `file:line` the two tickets name, checked on this branch. Ticket 04 names
no line numbers at all — it cites Q14 and the two specs by name — so the table
is ticket 03's, plus the map lines ticket 03 rests on.

| Cited at | Points to | True location | Match? |
|---|---|---|---|
| `03:13` → `store.py:162` | the `automatic_rules` refusal | `store.py:169-170` | **no** — `:162` is `"checksum": checksum,` in `migrate`'s return |
| `03:13` → `merge.py:303` | the `automatic_rules` refusal | `merge.py:303-304` | **yes** — `if policy is None or policy.get("automatic_rules"):` |
| `03:66` → `adapters.py:77-80` | "the kind is decided per record, never per source" | `adapters.py:77-84`; the decisive lookup is `:82` | **near** — the range starts right and stops two lines before `kind_values.get` |
| `03:120` → `030:35` | blocking disposition read | `030:35` | **yes** — `p->'body'->'blocking'=to_jsonb(NOT (coalesce(src.body->'nonblocking_deferred_reasons'…` |
| `03:120` → `030:59` | blocking disposition read | `030:59` | **yes** — the same comparison in the touched-reviews scan |
| `03:120` → `merge.py:495` | the Python blocking read | `merge.py:495` opens the `deferred_contracts` dict; the read is `:514-517` | **near** — points at the block, not the line |
| `03:74` → migration 031 | `mapping_version` | `031_clean_mdm_mapping_version.sql`, in `CLEAN_MDM_MIGRATIONS` (`store.py:50`) | **yes** |
| `03:102` → migration 032 | deferred `schema_version` check | `032_clean_mdm_deferred_reading.sql` (`store.py:51`) | **yes** |
| `03:102` → migration 027 | deferred natural key | `027_clean_mdm_deferred.sql` (`store.py:47`) | **yes** |
| `03:111` → `survivorship.AUTHORITY_SECTIONS` | authority-bearing sections | `survivorship.py:265` | **yes** |
| `03:79` → `023_clean_mdm.sql:50` (via `map.md:29-32`) | assertions keyed by `source_code` | `023:50` is `UNIQUE(source_code,record_key,publication_key)` on `mdm_v2.assertion` | **yes** — exact |
| `map.md:33` → `store.py:162` | same refusal | `store.py:169-170` | **no** — inherited from ticket 03 |
| `map.md:26-28` → "migrations 028-030" | the GLEIF/publication work | now through `032` | **stale, not wrong** |
| `map.md:24-26` → the six named `clean/` modules | "what already exists" | all six exist | **yes** |

Ticket 04's spec references, checked by content rather than line:

| Ticket 04 claim | Spec line | Faithful? |
|---|---|---|
| C1 declaration list | `company-policy.md:78-80` | **yes**, word for word, minus "verification evidence" (covered by C2) and `tolerance` (`policy-language.md:369`), which neither states |
| C2 verify, not measure | `company-policy.md:80-82` | **yes** |
| C3 missing/ambiguous/conflicting/suspended/unsupported | `company-policy.md:85-87` | **no** — spec says "does not gain binding authority"; ticket says "defers" |
| C4 LEI ≠ CIK crosswalk | `company-policy.md:87-89` | **yes**, near-verbatim; and enforced in code, since `merge.py:397-407` groups identifier conflicts per namespace |
| C5 name/lapse never revokes | `company-policy.md:89`, Q9 at `:19` | **yes**; and trivially satisfied, since `identity.replay` accepts `revoke` only against `override`/`exclude`/`reverse` (`identity.py:41-47`) and refuses to move an established bind at all (`:73-76`) — Q9's *positive* half (suspend the link, rebuild from remaining evidence) has no operation |

---

## What the operator should check by hand

1. **Whether two policy bodies holding one `(rule_id, version)` is acceptable**
   (F1). If not, decide where the refusal lives — `register_policy` comparing
   against already-registered bodies, or the assertion recording the rule that
   fired, or both. The second is the one that makes a committed row explain
   itself, and `policy-language.md:210-213` already requires it.
2. **How a proposal learns that a concurrent run minted its entity** (F2).
   Widening the assessment scope to the candidate key preserves both decision 1
   and Q13, and `apply`'s existing retry loop then does the rest — but it means
   changing what `assessment_snapshot` reads (`028:28-74`), and decision 1's
   wording ("the lookup and the write are never separated") should be restated
   to match what the two-transaction shape actually offers.
3. **What "a stable surviving ID" in the map's verification bar means**
   (F3) — stable across reordering within a partition, or across
   repartitioning. The second is a much stronger claim and constrains how
   decision 3 can be built.
4. **Whether decision 3's "same bar" is meant to cover measured rules** (F3).
   The recommendation is to scope the within-run match to §9.3 deterministic
   rules, mirroring ticket 02's own amendment.
5. **Which policy a read loads, and through which signature** (F4). Threading
   `manifest["policy_digest"]` from `cli.py:284` into `batch_evidence` and
   `prepare_native` is a two-parameter change today and a migration later.
6. **Whether the suspension row needs `namespace` in its key** (F5), before
   ticket 04 builds against ticket 02's build list as written.
7. **Whether `policy-person.json` should be corrected to `otherwise: true`**
   (F6). It is evidence rather than a fixture, so nothing breaks either way —
   but a document the spec describes as the worked example that "reads … to the
   row" should be loadable by the engine the spec is for.
8. **Whether `is_empty` should treat `0` as empty** (F8). Inherited from the
   prototype, unreachable today, and cheap to decide once rather than after a
   numeric source is registered.
