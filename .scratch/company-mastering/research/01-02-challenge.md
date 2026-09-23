# Challenge pass on tickets 01 and 02

Type: research
Date: 2026-09-22
Branch: `claude/company-mastering`
Subjects: `.scratch/company-mastering/issues/01-decide-dataset-contract-versioning.md`,
`.scratch/company-mastering/issues/02-settle-the-policy-execution-boundary.md`

## What I checked

Every `file:line` either ticket names, opened and read on this branch. The full
`edgar_warehouse/mdm/clean/` module (`evidence.py`, `store.py`, `survivorship.py`,
`consumer.py`, `adapters.py`, `merge.py`, `company_source.py`), migrations `023`
through `030` plus the migration list on `origin/main`, and the accepted specs
(`docs/specs/clean-mdm/company-policy.md`, `company-completion.md`, `merge-stage.md`,
`acceptance.md`, `docs/specs/mdm/policy-language.md`, `docs/specs/person/consumer.md`)
and `.scratch/handover/2026-09-20-codex-policy-language-reconciliation.md`.

I re-derived the Wilson sample-size arithmetic myself rather than trusting either
the ticket's or the spec's restatement, and worked the suspension-line arithmetic
explicitly.

## What I could not check

- **Nothing was executed.** No database, no migration run, no test run — so every
  claim below is a claim about source text, not about a live schema. `mdm migrate`
  does not run automatically on deploy (CLAUDE.md), so whether `030` is applied to
  any real instance is not knowable from the repo.
- **Whether Codex has since settled Q11's confidence coverage** off-repo. The last
  written word is `policy-language.md:466` ("Codex settles which Q11 means") and
  `.scratch/handover/2026-09-20-codex-policy-language-reconciliation.md:105-107`.
- **Whether the "two rows, current and one backup" retention is operationally
  sufficient** — that is a volume question, not a repo question.

## Verdict table

Ticket 01's own heading reads "### The five decisions" over six numbered items
(`01-...md:50`). Labels below follow the numbering, not the heading.

| # | The decision, in short | Verdict |
|---|---|---|
| 01-Q1 | A re-read keeps both rows; `source_code` never changes | **unsound** — the runtime refuses the second row (F1) |
| 01-Q2 | Two rows kept: current and one backup; older pruned | **unsound** — jointly unreachable with 01-Q3 (F3) |
| 01-Q3 | Except where a live decision still cites it | **sound**, but see F3 — the exception swallows the rule |
| 01-Q4 | Registration alone re-reads nothing | **sound** |
| 01-Q5 | Identity parts may never change within one `source_code` | **sound** |
| 01-Q6 | The version is a column, not part of the hashed body | **unsound** — not implementable as designed (F2) |
| 02-Q1 | One home per kind: `kinds.<kind>.fields` | **sound**, with an unnamed third call site (F6) |
| 02-Q2 | Classification governed by policy; decided kind stays on the evidence | **sound**, but answers only half its own question (F5) |
| 02-Q3 | A field records its kind's own digest, not the body's | **sound** — and correctly goes past what Codex flagged (F7) |
| 02-Q4 | Company 99.9% at 95%; Person 99% at 97.5% | **sound**, with two unaddressed consequences (F8) |
| 02-Q5 | Suspension in its own table keyed by the rule digest; `max_per_10k: 5` | **unsound** — scope error with an arithmetic consequence (F4) |
| 02-Q6 | Coherent field groups filled whole or left unknown | **sound**, but drops half of what question 6 asked (F9) |

**Count: 8 sound, 4 unsound, 0 unverifiable.**

The "unverifiable" bucket is empty, and that is a real result rather than a
courtesy. Every one of the twelve decisions names either a code site or a spec
line, and all of them exist. The tickets are checkable; four of them fail the
check. Three of the four failures are in ticket 01, and F1 and F2 between them
mean that ticket 01's central behaviour — a re-read adds a row — is refused by
the runtime whether or not migration 031 is ever written.

---

## Findings, most serious first

### F1 — 01-Q1: the runtime refuses the second row. A re-read raises `Conflict` on the first merge that loads the subject.

**What the ticket says.** "**A re-read keeps both rows** (Q1a). Registering a new
mapping version never rewrites an assertion. The old row stays exactly as it was,
and the new reading sits beside it." (`01-...md:53-57`). The migration design's
only survivorship note is "Survivorship orders by `mapping_version` after
`revision` and `publication_key` (`survivorship.py:41`)" (`01-...md:106-108`).

**What the repo says.** The line immediately below the one the ticket cites
rejects exactly that arrangement.

`edgar_warehouse/mdm/clean/survivorship.py:24-45`:
```python
groups = defaultdict(list)
for a in assertions:
    if a["source_code"] not in retired and (
        a["effective_at"] is None or instant(a["effective_at"]) <= instant(as_of)
    ):
        groups[a["subject"]].append(a)          # :29  — keyed by SUBJECT
...
for subject, versions in groups.items():
    seen = {}
    for a in sorted(versions, key=lambda a: (a["revision"], a["publication_key"], a["assertion_id"])):   # :41
        if a["revision"] in seen and seen[a["revision"]] != a["assertion_id"]:                            # :43
            raise Conflict("Source native revision has contradictory publications")                       # :44
        seen[a["revision"]] = a["assertion_id"]                                                           # :45
```

Trace the two rows of a re-read through it:

- **Same group.** `groups` is keyed on `a["subject"]`, and `subject` is
  `subject_key(source_code, record_key)` (`evidence.py:83`, `:34-35`). 01-Q1's whole
  point is that neither of those moves, so both rows land in the same group.
- **Same `revision`.** `revision` is taken from `publication["revision"]`
  (`adapters.py:165`). A re-read is of *the same publication*, so the revision is
  identical. Nothing in the ticket's design changes it, and nothing could — it is
  the source's own native revision, not the platform's.
- **Different `assertion_id`.** A mapping correction that actually changed the
  reading produces a different body, and `assertion_id = digest(body)`
  (`evidence.py:90`).

That is precisely the condition at `:43`, so `:44` fires:
`Conflict("Source native revision has contradictory publications")`.

**Reordering the sort does not help.** The ticket's one survivorship amendment
targets `:41`, the sort key. The guard at `:43-45` is a pairwise comparison over
equal revisions and is indifferent to sort order — whichever row arrives second
trips it. The ticket never mentions `:43-45`.

**Both rows do reach it.** `merge.py:67-69` keys the closure by id
(`stored_a[a["assertion_id"]] = a`), so two rows with different ids both survive
into `stored_a`, and `merge.py:368` passes the lot to `current_claims`. There is no
filter between the store and the guard.

**The two failure modes are exhaustive.** Take any record under a re-read:

| The re-read's body for that record | What happens |
|---|---|
| **differs** from the first reading | different `assertion_id`, same `revision`, same `subject` → `Conflict` at `survivorship.py:44` (this finding) |
| is **byte-identical** | same `assertion_id` → PK collision, `ON CONFLICT(assertion_id) DO NOTHING` silently drops the row (F2) |

There is no third case. Every record of a re-read either crashes the merge or
fails to produce a second row at all. "A re-read adds a row instead of rewriting
one" — the map's one-line summary of ticket 01 (`map.md:61-63`) — is not a
behaviour the current runtime permits for any record.

**What would have to change.** The guard at `survivorship.py:43-45` exists to catch
a real defect: one source native revision published twice with contradictory
content. A second mapping version of the same publication is *not* that, but the
runtime cannot currently tell them apart, because `mapping_version` is not
something it can see (F2). So this finding and F2 are one problem: the guard's
identity key has to become `(revision, mapping_version)` rather than `revision`,
which requires `mapping_version` to be visible to `current_claims`, which requires
it to be in the assertion body. That is the design decision 01-Q6 declined to make.
Ticket 01 needs to either re-open Q6 or explain how survivorship distinguishes the
two cases without it.

---

### F2 — 01-Q6: `mapping_version` cannot be a column outside the hashed body. Migration 031 is not implementable as designed.

**What the ticket says.** "The version is a column, not part of the hashed body
(Q5a). An assertion id is `digest(body)` (`evidence.py:90`); putting the version
inside the body would change every existing id and orphan every stored decision."
(`01-...md:78-82`). The migration adds `mapping_version bigint NOT NULL DEFAULT 1`
to `mdm_v2.assertion` and widens the uniqueness to include it
(`01-...md:86-93`).

**What the repo says.** Three facts, together, make this impossible without
amending code the ticket never names.

1. **There is no sibling channel in the batch payload.** The assertion row's
   `body` column *is* the batch item, inserted verbatim:

   `edgar_warehouse/mdm/migrations/023_clean_mdm.sql:166-168`
   ```sql
   INSERT INTO mdm_v2.assertion VALUES(item->>'assertion_id',item->>'source_code',item->>'record_key',
     item->>'publication_key',(item->>'revision')::bigint,(item->>'effective_at')::timestamptz,item,r->>'batch_id')
     ON CONFLICT(assertion_id) DO NOTHING;
   ```
   Every other column is projected out of `item`. A new column has to come from
   `item` too — i.e. from inside the body.

2. **The body is a closed 12-key set, enforced on every incoming assertion.**

   `edgar_warehouse/mdm/clean/evidence.py:94-115` rebuilds the body from exactly
   `source_code, record_key, publication_key, revision, effective_at, kind, fields,
   schema_version, identifiers, profiles, relationships, provenance` and then
   `if expected != body: raise Conflict("Normalized assertion hash or shape mismatch")`.
   `edgar_warehouse/mdm/clean/merge.py:238` calls `validate_assertion(a)` on every
   assertion in every batch. Any thirteenth key — including `mapping_version` —
   fails that comparison. So a "column not in the hashed body" has nowhere to ride.

3. **The stated fallback is circular.** The ticket's own bullet requires that
   "a batch produced by the backup version is still accepted while it exists"
   (`01-...md:104-105`). That means `commit_batch_core` must learn which mapping
   version produced *this* batch — which it cannot read off the dataset's current
   pointer, because the pointer names the current version, not the producing one.

**Compounding: the primary key, which the ticket never touches.**
`023_clean_mdm.sql:42` is `assertion_id text PRIMARY KEY`, and `:168` is
`ON CONFLICT(assertion_id) DO NOTHING`. The ticket proposes replacing only
`UNIQUE(source_code, record_key, publication_key)` and says that widening "is what
lets a second reading exist at all" (`01-...md:90-93`). It is not sufficient. If a
new mapping version reads one record to a byte-identical body — an added optional
field that is absent for that record, a corrected read that happens not to change
this value, a renamed output that does not reach this record — then `digest(body)`
is unchanged, the PK collides, and `ON CONFLICT(assertion_id) DO NOTHING` **silently
drops the insert**. No second row appears, and the surviving row still reports
`mapping_version = 1`. The ticket's claim "every row says which one produced it"
(`01-...md:69`) is then false for exactly the records a corrected mapping did not
change. There is also an explicit guard at `023_clean_mdm.sql:163-165` that raises
`'Assertion identity collision'` when the same `assertion_id` arrives with a
different body — so the two rows the design wants are precisely what the schema is
built to forbid. This is the second half of F1's exhaustive split: a re-read whose
body changed crashes survivorship, and a re-read whose body did not change never
becomes a row.

**One more, minor:** the ticket attributes the conflict clause to "`apply`'s
`ON CONFLICT(assertion_id) DO NOTHING`" (`01-...md:92-93`). `apply` is
`MergeStage.apply` (`edgar_warehouse/mdm/clean/merge.py:116`), Python; the SQL lives
in `mdm_v2.commit_batch_core`, which is `023_clean_mdm.sql:110`'s `commit_batch`
after `027_clean_mdm_deferred.sql:15` renamed it. Anyone writing 031 against the
name `commit_batch` will patch the wrong function — `028_clean_mdm_assessment.sql:124`
renamed the *then*-current `commit_batch` to `commit_batch_evidence` and `:141`
created a new one, so there are now three.

**What would have to change.** Either (a) `mapping_version` goes *into* the hashed
body — accepted with the cost the ticket rejected, which is that old ids do not
change (existing rows keep version 1 and their digest) but every *new* reading gets
a genuinely new id, which is arguably what the design wants anyway; or (b)
`assertion()`/`validate_assertion` gain an explicit out-of-digest envelope and
`commit_batch_core` is rewritten to project it, and the PK is changed from
`assertion_id` to `(assertion_id, mapping_version)` — a much larger migration than
the ticket describes. Either way, 031 as written in `01-...md:86-112` does not
compile against the code it targets.

---

### F3 — 01-Q2 and 01-Q3 cannot both hold. "Two rows" is unreachable because the citation surface is the whole history.

**What the ticket says.** "Per `(source_code, record_key, publication_key)` the
store keeps the current mapping version and the one before it. Older ones are
pruned." (`01-...md:59-62`), with the exception "A row that a live decision or
selected field points at is kept and marked superseded, and is pruned only once
nothing cites it" (`01-...md:63-67`), and the prune scoped to "where no decision and
no selected field cites the assertion id" (`01-...md:110-112`).

**What the repo says.** The brief asked whether a foreign key could be violated.
There is none — `grep -rn "REFERENCES mdm_v2.assertion" edgar_warehouse/mdm/migrations/*.sql`
returns zero rows. Nothing in the schema stops a prune. The problem is worse than
an FK: the citation surface is unbounded and lives in jsonb.

- **Every historical generation cites assertion ids.**
  `edgar_warehouse/mdm/clean/consumer.py:54-59` serves *any* generation by reading
  `b.effects->'projections'` for `b.generation<=:g`, and `:99` then runs
  `self._provenance(conn, body.get("fields", {}))` on whatever came back.
- **`_provenance` hard-fails on a missing row.**
  `consumer.py:29-37` looks the winner up by id and
  `if source is None: raise Conflict("Selected field has missing provenance")`.
- **The ids are written into the projection by survivorship.**
  `survivorship.py:55` (`"assertion_id": a["assertion_id"]` into each claim),
  `:191` (`current["evidence"].append(record["assertion_id"])` for profiles),
  `:212` (into review records), and `merge.py:335-336` into assessment scope.
- **The assessment path re-reads assertion bodies too**:
  `028_clean_mdm_assessment.sql:40` — `SELECT assertion_id AS id,body FROM mdm_v2.assertion`.

So "no selected field cites the assertion id" must be evaluated against the union
of `mdm_v2.projection.body` **and every retained `mdm_v2.batch.effects`** — that is,
all history, because time travel to any generation is a supported read. Any
assertion that has ever been selected is cited forever. The prune can only ever
remove rows that were never chosen, which is not the case 01-Q2 exists to bound.

**Verdict split.** 01-Q3 (the exception) is correct and necessary — without it the
consumer raises `Conflict` on a historical read. 01-Q2 (the bound) is unsound,
because the exception is not an exception, it is the normal case.

**What would have to change.** State a real retention rule that both survives time
travel and bounds growth. The honest options are: keep every assertion row and drop
01-Q2 entirely; or bound generation retention explicitly, so "cited" has a finite
horizon, and say what a read below that horizon returns. Silently keeping "two rows
plus anything cited" is a growth policy with no bound.

---

### F4 — 02-Q5: the suspension line is lifted out of the one place the spec scopes it to, and at face value it makes a rule at its own bar suspend itself.

**What the ticket says.** "Suspension lives in its own table, keyed by the rule
digest (Q5a). … The measured line stands: `warm_up_decisions: 10000`,
`max_per_10k: 5`." (`02-...md:62-67`), and the build list: "a suspension table and
the runtime check that reads it before **any automatic verdict**" (`02-...md:84-85`).

**What the spec says.** Those two numbers are not a general rule-error budget. They
are one field of the **Identifier Contract**, declared per namespace, in the
deterministic-activation section:

- `docs/specs/mdm/policy-language.md:257` — "Declared once per namespace under
  `kinds.<kind>.identifiers`."
- `:269` — the `tolerance` row: `{unit: items, warm_up_decisions: 10000, max_per_10k: 5}`,
  §9.3.
- `:362-366` — §9.3 `deterministic` activation: "A rule whose `when` is identifier
  primitives only **has no precision to measure**; its failure mode is a wrong
  identifier contract, not a wrong score."
- `:381-383` — "**Count distinct `(identifier, incoming normalized name)` items**,
  not records."
- `:384-387` — "Measured: never trips on 72,981 real decisions."

The 99.9% bar is §9.2 `measured` activation, on labelled held-out decisions
(`:328-353`, `docs/specs/clean-mdm/acceptance.md:40`). Different event, different
unit, different class of rule. **In the spec the two numbers do not conflict.**

**Where the conflict comes from.** Ticket 02 relocates the line twice over: it keys
the counter on *the rule*, and the build list fires it before *any* automatic
verdict — including §9.2 fuzzy rules, for which the spec declares no runtime
tolerance at all. Read that way, the arithmetic does not hold:

- Bar: `min_precision = 0.999` → tolerated error rate `0.001` = **10 per 10,000**.
- Line: `max_per_10k = 5` = `0.0005` → demands **99.95%** at runtime.
- `0.0005 < 0.001`. The runtime line is **twice as strict as the activation bar**.
- A rule whose true precision sits exactly at its bar produces `λ = 10` errors per
  10,000-decision window. `P(X ≤ 5 | Poisson(10)) ≈ 0.067`. It survives its first
  post-warm-up window about 7% of the time, and suspends permanently the other 93%
  — "review until a new policy version with a fresh verification is registered"
  (`02-...md:65-66`, matching `policy-language.md:388-391`).

So yes: **a rule activated at exactly its accepted bar suspends itself**, and does
so almost immediately. The two numbers cannot coexist under ticket 02's reading.
They coexist fine under the spec's, because `max_per_10k` never counted decision
errors.

**Two further defects in the same decision.**

1. **"The rule digest" names something that does not exist.** In Clean MDM, a
   digest is per *document*: `mdm_v2.policy(digest, body jsonb)`
   (`023_clean_mdm.sql:10-13`, cited at `policy-language.md:13`), and
   `:403` — "document never becomes a digest" — plus `:24`, `:63`. The spec's unit
   of rule identity is `rule.version`: `:428`, "A rule edit changes `rule.version`
   and orphans its activation entry." The only `rule_version` columns in the repo
   are `edgar_warehouse/mdm/database.py:1164` and `:1223` and
   `edgar_warehouse/mdm/generation.py:78`, which belong to the **legacy graph-generation
   subsystem**, not Clean MDM. A suspension table keyed by "the rule digest" has no
   key to use.
2. **A §9.3 rule can name several namespaces**, each with its own `tolerance`
   (`policy-language.md:367` — "every namespace the rule names has a contract …
   and a complete `tolerance` block"). Keying one counter on the rule collapses
   distinct per-namespace lines into one, which is a silent semantic change to the
   only line that was ever measured.

**What would have to change.** Scope the counter where the spec puts it: per
`(kind, namespace)` Identifier Contract, counting distinct `(identifier, incoming
normalized name)` items, firing only on §9.3 deterministic verdicts. If a runtime
line is also wanted for §9.2 measured rules — a reasonable thing to want — it needs
its own derivation consistent with that family's bar, and it cannot be `5/10k`
against a `0.999` bar. Key the row on `(policy_digest, kind, family, rule_id,
rule_version)`, which are things that exist.

---

### F5 — 02-Q2 answers where classification sits but not how it reaches `normalize`, which was half the question.

**What the ticket asked.** Question item 2: "**Where classification sits** in the
body, **and how it reaches `normalize`**" (`02-...md:15`).

**What the decision answers.** Where it sits (in the Mastering Policy, pointed at
by name and version from the Dataset Contract) and that the decided kind stays
stamped on the evidence (`02-...md:44-51`). The build list adds only "resolve the
classification rule a Dataset Contract names, and refuse **registration** when it is
absent" (`02-...md:81-82`).

**What the repo says the gap costs.**

- `edgar_warehouse/mdm/clean/adapters.py:60-62` — `def normalize(row, *, source_code,
  contract, publication)`. It has no policy and no connection. Classification today
  is entirely local to the contract: `:72-79` reads `mapping["kind_field"]` and
  `mapping["kind_values"]`. Resolving a *policy-held* rule at normalize time
  requires a signature change the ticket does not name.
- `register_dataset` (`store.py:181-248`) validates only
  `record_key_format`/`identifier_formats` against `{None, "sec_cik", "lei"}`
  (`:206`). Adding a policy lookup creates a **registration ordering constraint that
  does not exist today** — the Mastering Policy must be registered before any Dataset
  Contract that names one of its rules. `register_policy` (`store.py:160`) and
  `register_dataset` are independent, and `mdm_v2.dataset` has no reference to
  `mdm_v2.policy` (`023_clean_mdm.sql:43` references only itself). §10's registration
  checks (`policy-language.md:400-416`) contain no such item either.

The decision is not wrong — it is incomplete in a way that will surface as a
signature change and an ordering bug in ticket 03. Marked **sound** because what it
decides is correct and consistent; flagged because ticket 03 will discover the
missing half.

---

### F6 — 02-Q1 names two call sites of `policy["fields"]`; there are three, and the third is not an identity kind.

**What the ticket says.** "A kind's field rules move under `kinds.<kind>.fields` …
Changes `survivorship.py:200` and the local Company policy's registration."
(`02-...md:37-43`). Build list: "read field rules from `kinds.<kind>`, and refuse a
new-shape body that also carries a top-level `fields` block" (`02-...md:77-78`).

**What the repo says.** The citation is exact —
`edgar_warehouse/mdm/clean/survivorship.py:200`:
```python
for name, rule in policy.get("fields", {}).get(kind, {}).items():
```
and `edgar_warehouse/mdm/clean/company_source.py:62-72` is the old-shape body
(`"fields": {"company": {...}}`). Both are correctly named.

The third is `survivorship.py:283-285`:
```python
role_policy = {
    "fields": {p["role"]: policy.get("profile_fields", {}).get(p["role"], {})}
}
```
followed by `:291-298`, a recursive `select_fields(p["role"], ...)` call. This
**synthesises an old-shape body at runtime** and feeds it back through the same
reader at `:200` — so a reader that has been switched to `kinds.<kind>` will stop
finding profile field rules unless this construction is migrated too. And
`p["role"]` is a *profile role*, not an identity kind, so "one home per identity
kind" does not obviously cover it: profile field rules live under `profile_fields`,
a separate top-level block the decision never mentions.

Combined with the decision's own promise that "bodies already registered keep
working unchanged and stay frozen" (`02-...md:40-41`), `select_fields` must handle
**both** shapes indefinitely. The ticket says a frozen body keeps working but never
says who reads it — the build list names only the new path.

**What would have to change.** Ticket 03's first bullet should read "read field
rules from `kinds.<kind>.fields` *or* top-level `fields` depending on the body's
declared shape", and `survivorship.py:283-285` should build whichever shape the
enclosing body declared — or `profile_fields` should be explicitly declared out of
scope for 02-Q1.

---

### F7 — 02-Q3 is sound, but it puts two different digests under one key name without bumping `contract_version`.

**First, why the decision itself holds**, since it looks at a glance like it
contradicts Codex. Codex's reconciliation item 4 reads: "**Merely adding a kind version beside a
whole-body digest does not stop Company business-hash churn after a Person-only
edit**" (`.scratch/handover/2026-09-20-codex-policy-language-reconciliation.md:111-112`).

02-Q3 does not do that. It **replaces** the per-field digest: "A field value records
its kind's own digest (Q3a) … The whole-body digest stays on the batch."
(`02-...md:52-57`). Verified end to end:

- `survivorship.py:274` — `"policy_digest": policy_digest,` inside the selected
  field dict. The value threaded in is the whole-body digest
  (`merge.py:421` → `:249` → the batch's `policy_digest`).
- `consumer.py:41` — `"policy_digest": field["policy_digest"],` reads it back into
  `field_provenance`.
- `consumer.py:98` — `"business_hash": digest(body)` over the projection body,
  whose `fields` entries carry that value. So today a Person-only edit **does**
  churn every Company business hash, exactly as `policy-language.md:457-461`
  describes.

Replacing the per-field value with the kind digest breaks that chain. 02-Q3 is
sound and correctly goes past the thing Codex flagged as insufficient.

**The unaddressed consequence, which is the finding.** The kind digest is stored in the same jsonb key
under the same name. There is no column, no width, no constraint: it lives in
`mdm_v2.projection.body` (`023_clean_mdm.sql:66-72`, `body jsonb`) and in
`mdm_v2.batch.effects` (`:28`). The typed, FK-backed one —
`mdm_v2.batch.policy_digest text NOT NULL REFERENCES mdm_v2.policy(digest)`
(`:24`) — is untouched, which is correct. But a consumer response will then carry
**two different `policy_digest` keys with two different meanings**:
`projection.policy_digest` (whole body, `consumer.py:82` and `:128`) beside
`field_provenance[x].policy_digest` (kind digest, `:41`) — while
`consumer.py:92` still says `"contract_version": 2`. No existing consumer resolves
the field-level value against `mdm_v2.policy`, so nothing breaks today; it is a
silent contract change that deserves a version bump or a distinct key name.
`028_clean_mdm_assessment.sql:91` compares `effects->>'policy_digest'` to
`command->>'policy_digest'` — both batch-level, so that check is unaffected.

---

### F8 — 02-Q4 is right on the numbers but leaves two consequences on the floor.

**The figures all check out**, and the brief was right to ask where they came from.

| Figure | Where it actually appears |
|---|---|
| Company 99.9% at one-sided 95% | `docs/specs/clean-mdm/company-policy.md:21` (Q11); also `merge-stage.md:69`, `acceptance.md:40`, `policy-language.md:325-326` |
| Person 99% at one-sided 97.5% | `docs/specs/person/consumer.md:167`, `:622`; `policy-language.md:325` |
| `warm_up_decisions: 10000`, `max_per_10k: 5` | `policy-language.md:269`, `:384` |
| Q14 identifier-only activation without a precision study | `docs/specs/clean-mdm/company-policy.md:24` |
| "A rule with no bar for its family cannot be activated" | `policy-language.md:326` |

Quoting `company-policy.md:21` in full, since it is the load-bearing line:

> | Q11 | Independently qualify automatic consolidation to the same accepted 99.9%
> precision target, demonstrated by a one-sided 95% lower confidence bound, plus
> zero hard-veto violations in adversarial tests. …

**Note for the record:** the brief asked whether the Company figure appears in
`docs/specs/clean-mdm/company-completion.md`. **It does not** — `grep` for `99.9`
in that file returns nothing. What it does say is `:65-68`: "Choose an approved
cohort containing real linked records … **Pin the cohort before measuring
acceptance.**" The bar lives in `company-policy.md`, `merge-stage.md` and
`acceptance.md`.

**Two things the decision does not address.**

1. **Calling Person's bar "accepted" overstates it.** `02-...md:58-60` writes
   "Each kind keeps its own **accepted** bar … Person 99% at 97.5% (its own
   ticket)." Both primary sources mark it open:
   `policy-language.md:325` — "Person is 0.99 (**operator amendment, proposed to
   Codex**)"; `person/consumer.md:622` — "Person amendment to Q11 … | **open with
   Codex**".
2. **Choosing 95% for Company orphans the only proof in hand.** `validate()`
   "refuses … **a proof at a different confidence coverage**"
   (`policy-language.md:418-421`), enforced by the predicate at `:350`:
   `require proof.method == bar.method and proof.one_sided_confidence == bar.one_sided_confidence`.
   The existing measurement (research 18) is at 97.5% (`:463`), and Codex left the
   coverage explicitly unsettled (`:462-466`, "Codex settles which Q11 means";
   reconciliation `:105-107`). Picking 95% is the right call — it is what accepted
   Q11 says — but it means any 97.5% proof must be **re-scored at 95%** before it can
   activate anything, even though 97.5% is the more conservative bound. The decision
   should say so.

---

### F9 — 02-Q6 answers coherent field groups and drops publication-time ordering, which the same question asked for.

**What the question asked.** Item 6: "**Survivorship.** Coherent field groups
**and publication-time ordering**, with the acceptance tests that show them
working." (`02-...md:23-24`).

**What the decision answers.** Coherent field groups (`02-...md:68-73`). The only
mention of publication time is "within one source the later publication wins",
scoped *inside* a group.

**What the repo says is missing.** `docs/specs/clean-mdm/merge-stage.md:139-145`
gives the accepted total order:

```
1. Active evidence-bound stewardship override for that field/scope, if any.
2. Versioned source rank for `(identity kind, optional profile type, field)`.
3. Descending source effective time, with missing time sorted last.
4. Descending publication time where the field policy permits it.
5. Stable dataset code, source-record key, and assertion digest ascending.
```

`edgar_warehouse/mdm/clean/survivorship.py:239-249` implements 2, 3 and 5:
```python
eligible.sort(key=lambda c: (
    rule["sources"].index(c["source_code"]),
    -instant(c["effective_at"]).timestamp() if c["effective_at"] is not None else float("inf"),
    c["source_code"], c["record_key"], c["assertion_id"],
))
```
Rule 4 is absent, exactly as `policy-language.md:467-469` reports. Ticket 02's
build list (`:75-86`) names only "group-aware selection in
`survivorship.select_fields`", and none of the five acceptance tests
(`:90-94`) covers publication-time ordering. Codex's item 6
(reconciliation `:116-118`) asked for both, with tests.

Also note the decision's restatement drops the qualifier. The spec says "where the
field policy permits it"; the decision says flatly "the later publication wins".
That is a per-field opt-in in the spec and an unconditional rule in the ticket.

---

## Check B — migration 031: clean

Both checks the brief asked for come back **clean**, and it is worth recording
positively rather than by silence.

```
$ ls edgar_warehouse/mdm/migrations/ | tail -3
028_clean_mdm_assessment.sql
029_clean_mdm_family_checkpoint.sql
030_clean_mdm_evidence_disposition.sql

$ git ls-tree --name-only origin/main edgar_warehouse/mdm/migrations/ | tail -3
.../028_clean_mdm_assessment.sql
.../029_clean_mdm_family_checkpoint.sql
.../030_clean_mdm_evidence_disposition.sql
```

1. **`031` is the next free number** on this branch and on `origin/main`. PR #693
   is commit `0971a210 feat(mdm): complete native GLEIF Company evidence ingestion
   (#693)`, and it added **`030`**, not `031`. Nothing has merged since that takes
   the number: `origin/main` HEAD is `b9c0fc93` (#694, docs only).
2. **No migration `024`–`030` altered `UNIQUE(source_code, record_key,
   publication_key)`.** `025` adds four expression indexes
   (`025_clean_mdm_indexes.sql:2-7`); `026`, `027`, `028` create new tables;
   `029_clean_mdm_family_checkpoint.sql:2` alters `mdm_v2.checkpoint`;
   `030_clean_mdm_evidence_disposition.sql:3` replaces
   `mdm_v2.commit_batch_evidence` only. The constraint at
   `023_clean_mdm.sql:50` is current and ticket 01's read of it is **not stale**.

The one thing that *has* moved is the function name, not the constraint: the
assertion INSERT that was `mdm_v2.commit_batch` in `023` is now
`mdm_v2.commit_batch_core`, via `027_clean_mdm_deferred.sql:15`. See F2.

3. **No `031` exists on any ref**, not just the two the brief named:
   `git log --all --oneline --diff-filter=A -- 'edgar_warehouse/mdm/migrations/031*'`
   returns nothing. That said, this repo runs parallel runtimes, and there are two
   live Codex branches touching exactly this code —
   `codex/clean-mdm` and `codex/sec-gleif-company`, both with `origin/` remotes,
   plus `grok/aws-cleanup`. `--all` only sees remote-tracking refs as of the last
   fetch, so "free everywhere" is true as of this working copy and not a guarantee.
   See the hand-check list.

## Check C2 — the Proving Run can clear the bar, because the bar does not apply to it

The brief's suspicion here does not land, and the arithmetic is worth showing
because it is a **positive** result: the spec's numbers are internally consistent,
so the bar is not what is wrong.

**The derivation.** `policy-language.md:324` declares the method as
`wilson_lower_bound`. For `k = n` (zero observed errors) the Wilson lower bound
collapses to `n / (n + z²)`. Requiring `n/(n+z²) ≥ p` gives `n ≥ z²·p/(1-p)`:

| Bar | z (one-sided) | z² | Required n |
|---|---|---|---|
| 0.999 | 1.6449 (95%) | 2.7055 | **2,703** |
| 0.999 | 1.9600 (97.5%) | 3.8415 | **3,838** |
| 0.99 | 1.6449 (95%) | 2.7055 | **268** |
| 0.99 | 1.9600 (97.5%) | 3.8415 | **381** |

All four reproduce `policy-language.md:463-464` **exactly** ("n ≥ 268 vs ≥ 381 at a
99% bar; 2,703 vs 3,838 at 99.9%"). The brief's rule-of-three figure (`3/n`, giving
~3,000) is the Clopper-Pearson approximation and is the right order of magnitude;
Wilson is the declared method and gives 2,703.

**Why the Proving Run is nonetheless not blocked.** `02-...md:60-61`: "The bar gates
fuzzy rules only: Q14 identifier binding activates by verifying an Identifier
Contract, so tickets 04 and 05 do not wait on a precision study." That is exactly
the §9.2/§9.3 split (`policy-language.md:328` vs `:362-366`) and exactly
`company-policy.md:24` ("Identifier-only source binding may activate through a
verified, versioned Identifier Contract **without a separate statistical precision
qualification**"). Ticket 05 also does not pin a cohort *size* — it pins a
*manifest* ("a frozen CIK manifest (Company Q3) plus the verified GLEIF publication
already captured", `05-...md:11-13`), matching Q3 at `company-policy.md:13`. So the
premise "ticket 05's cohort must clear ticket 02's bar" is false. **No finding.**

**A forward constraint worth writing down, not a finding.** The largest labelled
Company data in hand cannot ever qualify a fuzzy rule at 99.9%/95%:

- 10,473 snapshot rows, 8,341 eligible, **1,000-row cohort**
  (reconciliation `:37`);
- 883 candidates, **308 accepted**, 502 no candidate, 103 rejected different, 87
  unresolved (`:38`);
- "Tier B's retained adjudication precision is **224/249 (89.96%)**; it does not
  establish the accepted Company automatic-rule gate. The 308 research links are
  not independent held-out truth" (`:60-62`).

2,703 clean labelled decisions are needed; 1,000 rows exist and 308 are adjudicated,
at 89.96% observed precision on the Tier B slice. Any future fuzzy Company rule
needs a labelling effort roughly 3× the existing cohort before the bar is even
reachable. That belongs in the map's "Not yet specified" section.

---

## Citation audit

Every `file:line` either ticket or the map names, against what is actually there.

| Cited as | Cited in | What is actually at that location | Match |
|---|---|---|---|
| `evidence.py:90` | 01-Q6 | `body["assertion_id"] = digest(body)` | **exact** |
| `evidence.py:82-90` | 02-Q2 | `"kind": kind,` (82) through the digest (90) | **exact** |
| `023_clean_mdm.sql:50` | 01 question, map | `UNIQUE(source_code,record_key,publication_key)` | **exact** |
| `023_clean_mdm.sql:160` | 01 answer preamble | `IF item->>'schema_version' IS DISTINCT FROM src.body->>'schema_version' THEN` | **exact** |
| `store.py:217-224` | 01 question, map | **off.** 217-219 are the registry-authority query params; 220-225 raise `Conflict("Dataset requires active acquisition registry coverage")` — a *different* guard. The dataset-body immutability check is **`store.py:232-239`**: `if current[0]["body"] != body … raise Conflict("Dataset contract is immutable; register a new versioned contract")` | **off — different guard** |
| `store.py:162` | map, ticket 03 | `if body.get("automatic_rules"):` in `register_policy` | **exact** |
| `merge.py:303` | map, ticket 03 | `if policy is None or policy.get("automatic_rules"): raise Conflict("Unknown or unqualified policy")` | **exact** |
| `survivorship.py:200` | 02-Q1 | `for name, rule in policy.get("fields", {}).get(kind, {}).items():` | **exact** |
| `survivorship.py:274` | 02-Q3 | `"policy_digest": policy_digest,` in the selected-field dict | **exact** |
| `survivorship.py:41` | 01 migration design | `key=lambda a: (a["revision"], a["publication_key"], a["assertion_id"]),` | **exact** |
| `consumer.py:31` | 01-Q3 | `JOIN mdm_v2.batch b USING(batch_id) WHERE a.assertion_id=:id` — reads the winning assertion by id, as claimed. The id is passed at `:34` | **exact enough** |
| `consumer.py:41` | 02-Q3 | `"policy_digest": field["policy_digest"],` | **exact** |
| `adapters.py:58-68` | 02-Q2 | **off.** 58-59 are blank/the tail of `record_key()`; 60-62 are `normalize`'s signature; 63-68 are its docstring. The kind logic is **`adapters.py:72-79`** (`kind = mapping.get("kind")` … `raise UnsupportedRecord("unsupported_identity_kind")`) and the stamp onto the assertion is **`adapters.py:167`** (`kind=kind,`) | **off — docstring, not logic** |
| `023_clean_mdm.sql:10-13` (`mdm_v2.policy`) | policy-language.md:13 | matches | **exact** |
| `merge-stage.md:137-139` (coherent groups) | policy-language.md:468 | 137-139 are the "first find the latest applicable version … total order" preamble; the coherent-group paragraph is **`merge-stage.md:152-156`** | **off** (spec's own citation, not the tickets') |
| `merge-stage.md:129` (publication-time tiebreak) | policy-language.md:468 | 129 is "Retract assertion" in the evidence-semantics table; the publication-time tiebreak is **`merge-stage.md:144`** | **off** (spec's own citation) |
| `survivorship.py:239-249` (skips both) | policy-language.md:469 | correct — the sort key omits publication time | **exact** |
| `merge.py:183-184`, `store.py:155-156` (the refusal §9.2 replaces) | policy-language.md:356-357 | **off.** The refusals are at `merge.py:303` and `store.py:162` | **off** (spec's own citation) |
| `domain-model.md:46-48` | policy-language.md:258-259 | not re-checked | — |
| `apply`'s `ON CONFLICT(assertion_id) DO NOTHING` | 01 migration design | the SQL is `023_clean_mdm.sql:168`, inside what is now **`mdm_v2.commit_batch_core`** (renamed by `027_clean_mdm_deferred.sql:15`). `apply` is `merge.py:116`, Python | **imprecise — see F2** |

**The compaction signature the brief suspected is real, and it is narrow.** Two of
the tickets' own citations are off — `store.py:217-224` and `adapters.py:58-68` —
and both fail the same way: right file, wrong lines, landing on a *different*
guard or on a docstring rather than the logic. The underlying claims are true at
the corrected lines in both cases. Every other ticket citation is exact. The three
additional off-by-N citations in the table are `policy-language.md`'s own, not the
tickets', and predate this branch.

---

## For the operator to check by hand

1. **Whether Codex has settled Q11's confidence coverage** since 2026-09-20.
   02-Q4 picks 95% on the strength of accepted Q11, which is right, but
   `policy-language.md:466` still reads "Codex settles which Q11 means" and the
   registration predicate at `:350` will refuse a 97.5% proof against a 95% bar.
   If research 18's measurement is meant to survive, it needs re-scoring.
2. **`git fetch --all`, then re-check that `031` is free.** Codex has two live
   branches in this exact code (`codex/clean-mdm`, `codex/sec-gleif-company`), and
   a concurrent runtime holding an unmerged `031` is the live risk that "free on
   two refs" does not cover. One `git log --all --diff-filter=A -- '.../031*'`
   after a fetch settles it.
3. **Whether migration `030` is actually applied** to the live MDM Postgres.
   CLAUDE.md is explicit that `mdm migrate` does not run on deploy. 031 will be
   written against a `commit_batch_core` whose current deployed state I could not
   verify.
4. **Whether `profile_fields` is in or out of 02-Q1's scope** (F6). This is a
   one-sentence answer the operator can give that saves ticket 03 a decision.
5. **Whether "two rows, current and one backup" is wanted at all** (F1, F2, F3), or whether
   the honest answer is that assertions are never pruned and generation retention
   is what gets bounded instead.
6. **Whether `max_per_10k: 5` was ever intended to apply outside §9.3** (F4). If
   the answer is no, 02-Q5 is a wording fix. If the answer is yes, a new line has
   to be derived per family and the 99.9% bar renegotiated against it.
7. **`.scratch/company-mastering/issues/01-...md:50`** — the heading reads "The
   five decisions" over six items. Cosmetic, but the map's summary line
   (`map.md:60-65`) enumerates five and folds Q6 into the trailing clause, so a
   reader skimming the map can miss that the column-not-body decision is a
   decision.
