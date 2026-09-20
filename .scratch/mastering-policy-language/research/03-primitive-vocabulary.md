# Research: the primitive vocabulary the policy language may call

Ticket: [03](../issues/03-define-primitive-vocabulary.md). Map:
[Mastering Policy Language](../map.md). Date: 2026-09-20. Read against the
`claude/mastering-policy-language` worktree (Clean MDM files read-only; `path:line`
citations are into that tree). Builds on
[research 01](01-policy-document-granularity.md) (document granularity, the digest
pin, the cross-kind closure) and [research 02](02-rule-activation-and-proof.md)
(activation per `(rule_id, rule_version, verdict)`, the proof block, the Merge
Stage predicate) — neither is re-derived here. This is a repository-extraction
task: every primitive below is taken from a rule this platform has already
written, and no primitive is proposed that no written rule needs.

## 1. The simple solution

**Twelve named tests are enough.** Every mastering rule this platform has written
so far — rule C-J's five classification steps, Person Tiers A–D, the GLEIF
Company binding contract, and Clean MDM's five-step field survivorship — decomposes
into twelve small, pure, boolean-or-winner functions, and the enormous parts of those
rules (the 90-odd legal-form tokens, the ambiguous-token list, the person suffixes,
the six structural field paths, the ordered source lists, the 0.99 and 0.999 bars)
are **parameters the document carries, not code**. Two of the twelve are shared
text/identifier normalizers, five do classification (is the evidence present; is a
field one of these values; does the name carry N tokens from this list; is the name
person-shaped; are all these fields empty), four do binding (does an identifier
match; is that identifier claimed more than once; is a compound context key equal;
is a name similarity above a floor), and one does survivorship (rank eligible claims
by the accepted five-step order). The single most useful thing the extraction shows
is that the *same* token list appears twice in this repo with **opposite** meanings —
rule C-J reads `TRUST`, `FUND`, `CO`, `HOLDINGS` as evidence that a name is an
entity (`18-classify.py:64-80`), while the legacy normalizer *deletes* the same
words before comparing names (`002_seed_data.sql:73-98`) — which is precisely why
lists belong in data and the test belongs in code: one primitive, two declared lists,
two opposite uses, and neither use requires a code change to retune. What the
vocabulary deliberately refuses is anything the operator cannot read and the Merge
Stage cannot replay: no document-supplied regexes, no SQL, no arbitrary expressions,
no clock or network reads, and — the repo-specific one — no way for a binding rule
to reach a survivorship primitive, because this repo's own glossary forbids
"source rank as permission to merge identities" (`CONTEXT.md:51`).

## 2. The primitives, by family

**How to read the table.** "Written rule that needs it" names a rule already
resolved in this repo, not a hypothetical. "Existing implementation" is where the
behaviour lives today — often in research code (`18-classify.py`) or legacy code
(`match.py`) rather than in Clean MDM, which is a finding in itself: most of this
vocabulary is *implemented somewhere and governed nowhere*.

Every primitive is a **pure function of declared evidence fields plus declared
parameters**. No I/O, no clock — `as_of` is an argument the interpreter passes in
(`survivorship.py:124`, used at `:220-226`), never a value the primitive reads.
This is research 02's own purity requirement for `qualified()` (`research/02:158-159`)
applied to the vocabulary.

**Raw versus normalized is part of each primitive's contract, and must be
declared per argument.** The reference implementation is deliberately mixed:
`person_name_shape` tests `&` and digits against the **raw** string
(`18-classify.py:141-142`, `raw = name.strip()`) and only *tokenizes* the
normalized one (`:147`), because `norm_name` rewrites `&` to ` AND ` before
anyone can see it (`:122`). A vocabulary that passed one `normalizer` argument
and ran the whole predicate after it would silently kill both checks. So each
argument that inspects text carries `applies_to: "raw" | "normalized"`, defaulting
to `"normalized"`; the JSON in §6 shows it on `name_shape`. The same rewrite is
why a declared token list must contain `"AND"` and not `"&"`: `_TOKEN_RE` runs on
the normalized name and `"&"` is only a *label* the separate ampersand branch
appends (`:133-135`). This is not a detail — it is the first thing the prototype
(ticket 04) will get wrong if the contract is left implicit.

### Family 0 — Shared normalization (2)

| Name | Parameters | Returns | Written rule that needs it | Existing implementation |
| --- | --- | --- | --- | --- |
| `normalize_text` | `field`, `policy_ref` (a named, versioned normalization: case, Unicode, punctuation, ampersand, suffix handling) | normalized string | C-J's whole name pipeline (`18-classify.py:120-126`, called by `entity_tokens` `:129` and `person_name_shape` `:147`); Person Tier B "exact **normalized** name" (`02-decide-what-binds-a-person.md:75`) | `18-classify.py:120-126` (`norm_name`: upper, `&`→`AND`, punctuation→space, collapse whitespace); legacy `edgar_warehouse/mdm/rules.py:152-170` (`_normalize_name_uncached`: lower, drop apostrophes, punctuation→space, strip `legal_suffix` seeds). **Two incompatible normalizers already exist** — hence the required `policy_ref`. Declared as a requirement at `docs/specs/clean-mdm/merge-stage.md:66-67`. |
| `normalize_identifier` | `field`, `namespace_format` (e.g. `sec_cik`) | normalized string, or a typed refusal | Person Tier A binds on `owner_cik` (`02:74`); GLEIF "verified deterministic crosswalk" (`gleif-company-augmentation/spec.md:84-86`) | `edgar_warehouse/mdm/clean/adapters.py:17-30` (`format_value`; `sec_cik` rejects non-digits/len>10/zero and zero-pads to 10) — already a per-namespace, config-selected format |

### Family 1 — Classification (5)

| Name | Parameters | Returns | Written rule that needs it | Existing implementation |
| --- | --- | --- | --- | --- |
| `evidence_present` | `document` (a declared evidence reference, e.g. the owner's captured `submissions.json`) | bool | C-J step 0: no captured `submissions.json` → **deferred**, "never decide from the row alone" (`03-decide-reporting-owner-classification.md:43`) | `18-classify.py:302-305` + `:312` (`sub_present: True` only when the bronze file exists), `:361`/`:367` (absent → `sub_present: False`); consumed at `:676-677`, reached by C-J through `:702` |
| `field_in_set` | `field`, `values[]` | bool | C-J step 1: SEC `entityType ∈ {operating, investment}` → **company** (`03:44`); also gates "`entityType='other'` is evidence, never a decider" (`03:54`) by simply not listing `other` | `18-classify.py:678` (`r.get("entity_type") in ("operating", "investment")`); the same shape is already config-driven in Clean MDM at `clean/adapters.py:62-66` (`kind_field` + `kind_values` map) |
| `token_match` | `field`, `normalizer`, `token_list` (declared list), `exclude` (declared list, optional), `min_count`, `max_count` | bool | C-J step 2 (`min_count:1`, `exclude: ambiguous` — an *unambiguous* token → entity, `03:45`); C-J step 3 (`negate`, `min_count:1` — no token at all → person, `03:46`); C-J step 2-guard (`min_count:1, max_count:1` — exactly one token, `03:45`) | `18-classify.py:128-137` (`entity_tokens`, whole-word match over `ENTITY_TOKENS` `:64-80` compiled at `:81-84`); the three parameterizations are materialized at `:273` (`has_entity_token`), `:274` (`has_unambiguous_token`, i.e. `exclude=AMBIGUOUS_TOKENS` `:85-87`) and `:704` (`len(entity_tokens) == 1`) |
| `name_shape` | `field`, `normalizer`, `min_tokens`, `max_tokens`, `suffix_list` (declared), `forbid_digits` + `forbid_characters[]` (each with `applies_to`, see the preamble — both run on **raw** text in the reference) | bool | C-J step 3 and step 2-guard: "person-shaped" (`03:46`, `:45`) — 2-5 alphabetic words, suffixes allowed, no digits, no `&` (`03:37-38`) | `18-classify.py:139-151` (`person_name_shape`), with `_PERSON_SUFFIX` at `:89` |
| `fields_all_empty` | `fields[]` (declared paths) | bool | C-J step 3 and step 2-guard: "structurally empty" — `sic`, `stateOfIncorporation`, `ein`, `tickers`, `ownerOrg`, `fiscalYearEnd` all empty (`03:38-39`, `:45-46`) | `18-classify.py:488-495` (`_structural_empty` over `_empty`, where `_empty` treats `None`/`""`/`0`/`[]`/`{}` alike) |

### Family 2 — Binding and consolidation (4)

| Name | Parameters | Returns | Written rule that needs it | Existing implementation |
| --- | --- | --- | --- | --- |
| `identifier_match` | `namespace` (e.g. `sec.owner_cik`, `adv.owner_id`, `gleif.lei`), `normalizer` | matching identity, or none | Person Tier A: "shared cross-reference id → auto, deterministic" (`02:74`); Person `#2` "a cross-reference id points at exactly one Person" (`02:63-66`); GLEIF rule 2, "verified deterministic crosswalk … that passes domain semantics" (`spec.md:84-86`) | Legacy `edgar_warehouse/mdm/match.py:65-85` (`CIKExactMatcher`, score 1.0, `AUTO_MERGE`) — the cleanest existing statement of the primitive. In Clean MDM the equivalent lookup is the decision-graph join, not a matcher: `clean/merge.py:60-62` (`body->>'subject'=ANY(:keys)`) and `clean/identity.py:69-79` (`bind` replay) |
| `identifier_cardinality` | `namespaces[]`, `max_identities_per_value`, `max_values_per_identity`, `on_violation` (`veto_to_review`) | bool (veto) | Person `#2`: "A second *Person* claiming a bound id is a hard veto → review" (`02:66`); GLEIF: "one active LEI binding per Company, one active Company per LEI. A conflicting candidate is a hard veto into review, never a silent rebind" (`spec.md:97-98`) | `clean/identity.py:73-76` (moving an established binding raises `Conflict`) — enforces one side (one identity per subject) unconditionally; the *other* side (one value per identity, and the cross-namespace case) has no implementation |
| `compound_key_equal` | `components[]` — each `{field, normalizer, comparison}` where `comparison ∈ {exact, consistent}` | bool | Person Tier B: "same issuer/firm CIK + exact normalized name + consistent role/flag" (`02:75`) | Legacy `match.py:123-131` (`context_fields`: every named context field must be present on both sides and string-equal, else the score is capped below `auto_min`). That is the same test, expressed as a penalty rather than a conjunct |
| `name_similarity` | `field`, `normalizer`, `algorithm`, `algorithm_version`, `min_score` | bool | Person Tier C: "fuzzy name, or name across different issuers → Steward review" (`02:76`); Person Tier D: "below the review floor → reject" (`02:77`) — C and D are separated only by a score floor | Legacy `match.py:90-100` (`_jw`, Jaro-Winkler via `jellyfish`) with thresholds seeded per `(entity_type, match_method)` at `002_seed_data.sql:61-66` (person `fuzzy_name` 0.92/0.80). **Clean MDM explicitly condemns this implementation**: "Pin the similarity dependency and algorithm. Missing implementation is a hard failure, not the current optional length-based fallback in `match.py`" (`merge-stage.md:67-69`) — referring to the `jellyfish is None` length-ratio fallback at `match.py:91-99` |

### Family 3 — Survivorship and projection (1)

The survivorship family is small for a structural reason worth stating plainly:
**the accepted spec fixes the total order, so the document supplies only the rank
list and the eligibility parameters.** `merge-stage.md:123-130` says "Then select
among eligible sources by this total order: 1. override … 2. versioned source rank …
3. effective time … 4. publication time … 5. stable key". Steps 1, 3 and 5 take no
declared parameter at all, so they are unconditional interpreter behaviour, not
callable primitives (§3 argues this).

| Name | Parameters | Returns | Written rule that needs it | Existing implementation |
| --- | --- | --- | --- | --- |
| `select_by_source_rank` | `sources[]` (ordered), `clear_sources[]`, `allow_unknown_effective`, `max_age_days` | winner claim + retained conflicts | GLEIF field authority: "Selection order is Clean MDM's accepted policy … this consumer supplies its versioned rank, it does not invent a second order" (`spec.md:145-148`); the installed Company policy is exactly this shape (`clean/company_source.py:62-72`); legacy `mdm_field_survivorship`'s `source_priority` / `preferred_source_order` rows (`002_seed_data.sql:44-56`) are the same idea in a table | `clean/survivorship.py:200-280` — eligibility at `:203` (`source_code in rule["sources"]`), `:205-207` (`clear_sources`), `:216-219` (`allow_unknown_effective`), `:220-226` (`max_age_days` against `as_of`); ordering at `:239-249` (`rule["sources"].index`, then `-effective_at`, then `source_code`/`record_key`/`assertion_id`); override precedence at `:228-238`, `:250-265`; retained conflicts at `:275-279` |

### Candidates the extraction surfaced but the minimum does not include (4)

Listed here because a reader who walks the same corpus will find them and should
know they were considered, not missed. §3 argues each one out.

| Name | Why it is not in the minimum | Evidence |
| --- | --- | --- |
| `kind_compatible` | Already unconditional interpreter behaviour, not a declarable test | `clean/identity.py:94-95` (`Incompatible identity kinds` on merge); `clean/merge.py:236-239` (`kind_conflict` review when a claim's kind ≠ the identity's). Person 03 makes the same point as policy: a kind correction is "review + bounded rebuild, never an entity merge" (`03:88-90`) |
| `digest_tuple` | No written rule needs a materialized blocking key — Person `#3` requires an *exhaustive* attempt: "No Person is created without a match attempt against every existing Person" (`02:67-68`) | Implementations exist but are interpreter-internal: `clean/evidence.py:34-35` (`subject_key`), `clean/survivorship.py:12-18` (`profile_key`) |
| `field_group_together` | Accepted Clean MDM policy with **no consumer and no implementation** today | Declared at `merge-stage.md:137-139` ("declare coherent field groups, such as address components, that must select one source assertion together") and `acceptance.md:42`. Grep of `clean/` finds no field-group logic; `survivorship.py:200-280` loops strictly per field. The one consumer that has addresses keeps them *evidence-only* (`spec.md:131-138`) |
| `publication_time_desc` | A rule **parameter** ("where the field policy permits it"), feeding the fixed order — and also unimplemented | `merge-stage.md:129`; absent from the sort key at `survivorship.py:239-249`, which goes rank → effective time → stable key, skipping step 4 |

## 3. The minimum vocabulary, and what could be a parameter instead

**The answer: the twelve primitives in Families 0–3.** Remove any one and a rule
this repo has already resolved cannot be written. The test applied to each was
"name the written rule that becomes inexpressible", not "would this be useful".

### Why each of the twelve is load-bearing

- Drop `normalize_text` → Tier B's "exact normalized name" (`02:75`) has no
  definition of *normalized*, and C-J's token and shape tests lose their input
  (`18-classify.py:129`, `:147` both call it).
- Drop `normalize_identifier` → Tier A cannot state that `0000320193` and `320193`
  are the same CIK (`adapters.py:20-29`).
- Drop `evidence_present` → C-J step 0 disappears, and the rule decides from the
  row alone, which `03:43` forbids in as many words.
- Drop `field_in_set` → C-J step 1 disappears and reporting-owner rows for operating
  companies stop routing to Company (`03:44`).
- Drop `token_match` → C-J steps 2, 2-guard and 3 all disappear; it is the single
  most-used primitive in the corpus, with three distinct parameterizations
  (`18-classify.py:273`, `:274`, `:704`).
- Drop `name_shape` → steps 2-guard and 3 disappear, and step 3's ~841 automatic
  `person` verdicts have no basis (`03:46`).
- Drop `fields_all_empty` → the same two steps disappear.
- Drop `identifier_match` → Tier A is gone and every binding becomes heuristic,
  which contradicts both `02:74` and `spec.md:84-86`.
- Drop `identifier_cardinality` → the two hard vetoes written in the corpus
  (`02:66`, `spec.md:97-98`) cannot be declared.
- Drop `compound_key_equal` → Tier B is gone; it is the operator's own
  "auto merge 80 to 99%, don't want to create manual work" decision
  (`02:50-52`).
- Drop `name_similarity` → Tiers C and D collapse into one bucket, losing the
  "reject, disposition recorded" floor (`02:77`).
- Drop `select_by_source_rank` → survivorship has no declarable rule at all; the
  installed Company policy (`company_source.py:62-72`) stops meaning anything.

### The four judgement calls, argued both ways

**1. `kind_compatible` — primitive, or unconditional behaviour?**
*For a primitive*: `merge-stage.md:45` lists "Compatible legal kind" as a *required
guard* in the per-kind evidence table, which reads like something a kind document
declares; and a future kind might want a narrower compatibility rule (a Fund
Structure that may bind to a Company, say) that the current hard refusal cannot
express. *Against*: the code already enforces it unconditionally in two places
(`identity.py:94-95`, `merge.py:236-239`), it takes no parameter any written rule
varies, and making it callable invites a document that *omits* it — turning a
currently-unbreakable invariant into one a policy edit can switch off.
**Recommendation: keep it unconditional.** A guard that a document could forget is
worse than a guard the document cannot mention. Revisit only when a second kind
pair genuinely needs asymmetric compatibility.

**2. `digest_tuple` — primitive, or absorbed?**
*For*: at production scale an exhaustive Person-vs-Person comparison is quadratic,
and a blocking key is the standard fix; the implementations already exist
(`evidence.py:34-35`, `survivorship.py:12-18`). *Against*: Person `#3` deliberately
says "a match attempt against **every** existing Person" (`02:67-68`), and a blocking
key silently changes *which* pairs are considered — a recall change disguised as an
optimisation, invisible in the proof block research 02 designed (which measures
precision, `research/02:113-121`). **Recommendation: absorb it into
`compound_key_equal` and leave blocking out of the vocabulary.** If blocking is later
needed, it is a separate decision with its own recall measurement, not a primitive
added quietly.

**3. `field_group_together` — primitive, or premature?**
*For*: it is *accepted* Clean MDM policy (`merge-stage.md:137-139`, `acceptance.md:42`),
and the map's destination says every written rule must be expressible; leaving it out
means the first consumer that needs coherent addresses forces a vocabulary change,
which by the Q2 boundary is a code change. *Against*: it has **no implementation**
(`survivorship.py:200-280` is strictly per-field) and **no consumer** — the only
Company consumer with addresses keeps them evidence-only (`spec.md:131-138`), and
Person's field set is still open (Person ticket 04). Adding it now means writing the
vocabulary's only unexercised entry, and the map explicitly forbids "nothing
speculative added" (`issues/03:14`). **Recommendation: leave it out, and record it as
the one accepted-but-unexpressible rule** so the gap is visible rather than
discovered. Worth telling Codex directly: this is a declared policy with no code
behind it, found while extracting the vocabulary, independent of this map.

**4. The ordering steps (override, effective time, stable key) — primitives, or
interpreter behaviour?**
*For primitives*: naming all five steps makes the accepted total order legible in the
document itself, and step 4 genuinely is conditional ("where the field policy permits
it", `merge-stage.md:129`). *Against*: steps 1, 3 and 5 take no parameter any document
varies — `survivorship.py:239-249` hard-codes exactly that order — so naming them
creates the *appearance* of choice where there is none, and a document that reordered
them would violate accepted policy while looking well-formed.
**Recommendation: one primitive (`select_by_source_rank`) whose contract is "apply the
accepted order", with the one conditional step exposed as a rule parameter
(`allow_publication_time_tiebreak`), not as a primitive.** Note for Codex that the
parameter has nothing to honour it yet.

### What is emphatically a parameter, not a primitive

Everything big in these rules. The 90-plus entries of `ENTITY_TOKENS`
(`18-classify.py:64-80`), the 27 `AMBIGUOUS_TOKENS` (`:85-87`), the 16
`_PERSON_SUFFIX` entries (`:89`), the six structural field paths (`:492-495`), the
`{operating, investment}` set (`:681`), the ordered `sources` list
(`company_source.py:66-71`), `max_age_days`, `clear_sources`, the 0.99 and 0.999
bars (`02:75`; `spec.md:110-112`), and the 0.92/0.80 similarity floors
(`002_seed_data.sql:61-66`). By the Q2 boundary each of these is a data edit; a new
*kind* of test is a code edit. The clearest evidence that this line is drawn in the
right place is the token-list collision: `TRUST`, `FUND`, `CO`, `LTD`, `LLC`, `CORP`,
`INC`, `HOLDINGS`, `PARTNERS`, `ASSOCIATES`, `SERVICES`, `GROUP`, `COMPANY` all appear
in *both* `ENTITY_TOKENS` (`18-classify.py:64-80`, where they are evidence that a name
is an entity) and the legacy `legal_suffix` seeds (`002_seed_data.sql:73-98`, where
they are deleted before names are compared). Same words, opposite semantics, one
primitive family. If the lists were code, retuning either use would be a deploy.

## 4. What the vocabulary deliberately cannot express

Six exclusions. The first three are generic; the last three are specific to this
repo and are the ones worth putting in front of Codex, because they are statically
checkable at registration rather than merely discouraged.

**1. No document-supplied regular expressions, SQL, or arbitrary expressions.**
What breaks if allowed: *replay* — a pinned digest would no longer determine a
result, because the regex engine and its Unicode tables are properties of the
build, not of the body, so the same document could classify differently on two
images (the exact hazard `merge-stage.md:66-68` is guarding against when it demands
a *versioned* normalization policy). *Determinism* — SQL pulls in collation,
`NULL` ordering and session timezone, all of which this platform has already been
burned by in the Snowflake loaders. *Review* — research 02's proof block attributes
a measurement to a `(rule_id, rule_version, verdict)` (`research/02:47-57`); a
reviewer can only re-score a rule they can read, and Person 03 records "the step
(0-4) that fired" as durable provenance (`03:86`), which an opaque expression cannot
supply. Note the precise line: C-J's *implementation* is regex-based
(`18-classify.py:81-84`), but the regex is **built by the primitive from a declared
token list**. The document says `["LLC","LP",...]`; the code compiles it. That is the
boundary — declared data compiled by versioned code, never a pattern the document
authors.

**2. No clock, no network, no read of anything outside the declared evidence.**
Primitives take `as_of` as an argument (`survivorship.py:124`, `:220-226`). C-J's own
release gate says the same thing for its input: "The classifier reads the **bronze**
`submissions.json`, never a live SEC fetch" (`03:98-99`). What breaks: a batch pinned
to digest D would not reproduce, which is the single property `merge-stage.md:92-99`
and `merge.py:173-184` exist to preserve.

**3. No loops, recursion, or aggregation across other identities.** Every primitive
sees one record and its declared evidence. What breaks: the bounded closure budget
(`merge.py:79-80`, `:103-104`, which reject a component over budget *before any
writes*) and "Freeze candidate generation against the declared watermark"
(`merge-stage.md:97`) — both assume the work a rule implies is knowable before it runs.

**4. A binding rule cannot call a survivorship primitive, and vice versa — enforced
statically, by family.** This repo's glossary states it twice, as *Avoid* lines:
Merge Stage avoids "identity consolidation by field priority" (`CONTEXT.md:23`) and
Field Survivorship avoids "source rank as permission to merge identities"
(`CONTEXT.md:51`); `merge-stage.md:90` says it a third time ("Survivor selection does
not determine which source wins any master field"). Today that is prose. Typed
families make it a registration-time check: a `family: "binding"` rule that names
`select_by_source_rank` is refused, in exactly the fail-closed shape research 02 gave
`qualified()` (`research/02:163-183`). What breaks if allowed: two identities merge
because one source outranks another, which is the specific failure the glossary was
written to prevent.

**5. A binding rule cannot decide on similarity alone.** The GLEIF contract puts it in
the tier table itself — "exact or fuzzy **name match alone** | never sufficient, in any
tier" (`spec.md:95`) — and Clean MDM's per-kind guard row for Person says "Shared name
or employer alone is insufficient" (`merge-stage.md:46`). Checkable: a rule emitting
`bind` whose `when` list contains only `name_similarity` predicates is refused at
registration. What breaks if allowed: the 90.0%-accepted Tier B measurement in the
GLEIF corpus (`spec.md:93`) becomes an *unattended* link rather than a candidate —
and `merge-stage.md:69-70` has already said why the number is not a licence
("A rule's similarity score is not itself a probability of identity").

**6. No boolean operators inside a step — no `OR`, no nesting.** A step's `when` is a
flat list of predicates, all of which must hold; `negate` is a per-predicate flag
(C-J step 3 needs it: "no legal-form token **at all**", `03:46`). Alternatives are
expressed as two steps with the same verdict. What breaks if allowed: exactly one step
can no longer be named as the cause of a verdict, and Person 03's recorded provenance
is "the step (0-4) that fired" (`03:86`). This is also what makes the worked example
below readable as a table by the operator who approved it.

## 5. How a primitive is versioned

**Clean MDM states the requirement, not the mechanism.** `merge-stage.md:66-70` is
three sentences: normalize names with "a versioned Unicode normalization,
case-folding and whitespace policy"; "Pin the similarity dependency and algorithm";
"Missing implementation is a hard failure, not the current optional length-based
fallback in `match.py`" — that last clause pointing at `match.py:91-99`, where a
missing `jellyfish` silently degrades Jaro-Winkler to a length ratio. So Clean MDM has
already decided *that* normalizers and similarity must be versioned and pinned, and
has already named the exact anti-pattern (a primitive that changes behaviour by
environment). It does not say how. The proposal below is the mechanism; the
requirement is not this research's to invent.

**The mechanism: reference every primitive as `name@version`, and fail closed on an
unknown pair.** The document writes `token_match@1`, `normalize_text@edgar-conformed-v1`,
`name_similarity@jaro_winkler-jellyfish-1.0.3`. The interpreter holds a registry keyed
by `(name, version)` and refuses a body naming a pair it does not have — the same
fail-closed shape research 02 gave `qualified()` (`research/02:163-183`), run in the
same two places (`store.py:155-156` at registration, `merge.py:183-184` per batch).

**What happens when behaviour changes.** Four cases, and only one is hard:

1. **A token or suffix is added to a list.** *Nothing happens to the primitive.* The
   list lives in the document, so the edit re-digests the body, mints a new digest,
   and every batch pinned to the old digest replays against the old list. This is the
   practical payoff of the parameter/primitive line in §3, and it covers the most
   frequent kind of change by a wide margin — C-J's list was tuned repeatedly during
   research 18, and `ENTITY_TOKENS`' own comment records it (`18-classify.py:62-63`:
   "Ticket 03 item 3 lists the core set; the rest are additions seen in this corpus").
2. **A field path or threshold changes.** Same — a parameter, so a document edit.
3. **A primitive's own logic is corrected** (say `name_shape` starts accepting
   hyphenated surnames). A *new version* is registered; the old version is not
   modified. The document must be edited to name the new one, which re-digests it.
   Old batches replay naming the old version. Silent in-place correction is the one
   thing forbidden, because it changes results under an unchanged digest.
4. **A pinned third-party dependency changes** (`jellyfish` bumps and Jaro-Winkler
   shifts in the sixth decimal). This is why the version string must name the
   dependency and its version, not just the algorithm — `merge-stage.md:67` says "Pin
   the similarity dependency **and** algorithm", two things, deliberately.

**The part that must be said plainly: replay needs the old implementation still in
the build.** The digest guarantees the document is unchanged; it guarantees nothing
about the code the document names. So "an old pinned batch replays identically" is
true only on a build that still contains `name_shape@1`. Two options:

- **Retain superseded versions indefinitely.** Replay is genuinely exact. The cost is
  code that can never be deleted, and a registry that grows monotonically — which is
  the same bargain Clean MDM already accepts for policy rows (append-only,
  `023_clean_mdm.sql:102-103`) and for decisions (replayed, never rewritten,
  `identity.py:20-33`).
- **Allow retirement with a declared floor.** Cheaper, but the guarantee weakens to
  "replays identically on a build at or above version *V*", and a batch pinned below
  the floor becomes unreplayable — which `merge-stage.md:92-99` treats as a
  correctness property, not an operational nicety.

**Recommendation: retain, and record the retention explicitly** rather than leave it
implicit. Clean MDM's own precedent supports it: `merge-stage.md:100-104` already
concedes that a fresh rebuild from source bytes alone "cannot be called exact-ID
replay" and must either restore the approved registry or prove parity through a
verified crosswalk — i.e. this platform has already chosen "retain the history" over
"recompute from scratch" once, for decisions. The primitive registry is the same
choice for code. The cost is real and should be stated to Codex as a cost, not
waved away: a vocabulary with a long tail of retained versions is a maintenance
burden that only a bounded, small vocabulary makes tolerable — which is the other
reason the answer to §3 is twelve and not fifty.

## 6. Worked example

Two rules in the proposed vocabulary. C-J is fully activated for one verdict;
Tier B is deliberately **not** activated, because its calibration (Person ticket 17)
is open — which is what makes it the better demonstration of research 02's
per-`(rule_id, rule_version, verdict)` activation.

**Placement caveat.** C-J appears below under `kinds.person.classification`, matching
research 02's example body (`research/02:95`). Research 01 §2 reason 3 argues
classification belongs in `mdm_v2.dataset.body.adapter` instead, because
`clean/adapters.py:58-68` assigns a kind from the per-source dataset contract
*before* the policy is loaded (`research/01:73-94`, and its own open item at
`research/01:283-290`). The vocabulary is identical either way; only the home
differs, and the home is the map's open "Authoring surface" item. Not decided here.

### Rule C-J

Steps are evaluated in listed order; the first step whose `when` list holds entirely
supplies the verdict. Step `2-guard` precedes step `2` because the written rule states
it as an *unless* clause (`03:45`), and first-match ordering is how an unless is
expressed without nesting (§4, exclusion 6).

```json
{
  "rule_id": "C-J",
  "version": "2026-09-20",
  "family": "classification",
  "evaluated_per": "sec.owner_cik",
  "emits": ["person", "company", "entity_undetermined", "deferred"],
  "lists": {
    "entity_legal_form": ["LLC", "L L C", "LP", "LLP", "LTD", "LIMITED", "INC",
      "CORP", "CORPORATION", "CO", "COMPANY", "TRUST", "FUND", "PARTNERS",
      "HOLDINGS", "CAPITAL", "MANAGEMENT", "FOUNDATION", "ESTATE", "ASSOCIATES",
      "GROUP", "BANK", "PLAN", "AND", "...91 entries, 18-classify.py:64-80"],
    "_note_AND": "'AND', not '&': norm_name rewrites & to ' AND ' (18-classify.py:122) before _TOKEN_RE runs, and '&' is only the label the ampersand branch appends (:133-135).",
    "ambiguous": ["CO", "TR", "SA", "AG", "AB", "AS", "SE", "OY", "KG", "GP",
      "LIFE", "MASTER", "GLOBAL", "ENERGY", "FAMILY", "LIVING", "SYSTEM",
      "CREDIT", "DELAWARE", "CAYMAN", "PLAN", "CHURCH", "BANK", "EQUITY",
      "CAPITAL", "SPONSOR", "TRUSTEE"],
    "person_suffix": ["JR", "SR", "II", "III", "IV", "V", "MD", "PHD", "ESQ",
      "CPA", "CFA", "DDS", "DR", "MR", "MRS", "MS"],
    "structural_fields": ["sec.submissions.sic", "sec.submissions.stateOfIncorporation",
      "sec.submissions.ein", "sec.submissions.tickers", "sec.submissions.ownerOrg",
      "sec.submissions.fiscalYearEnd"]
  },
  "normalizers": { "conformed": "normalize_text@edgar-conformed-v1" },
  "steps": [
    {
      "step": 0,
      "verdict": "deferred",
      "note": "No captured submissions.json; capture first, not a Steward item.",
      "when": [
        { "primitive": "evidence_present@1", "negate": true,
          "args": { "document": "sec.submissions.owner" } }
      ]
    },
    {
      "step": 1,
      "verdict": "company",
      "note": "Binds to the Company Identity by CIK under the Company document's Tier A.",
      "when": [
        { "primitive": "field_in_set@1",
          "args": { "field": "sec.submissions.entityType",
                    "values": ["operating", "investment"] } }
      ]
    },
    {
      "step": "2-guard",
      "verdict": "deferred",
      "note": "Surname guard: a person-shaped, structurally empty name carrying exactly one token ('Trust Jane', 'Council LaVerne H'). Post-hoc; see release gate 2.",
      "when": [
        { "primitive": "token_match@1",
          "args": { "field": "owner_name", "normalizer": "conformed",
                    "token_list": "entity_legal_form", "min_count": 1, "max_count": 1 } },
        { "primitive": "name_shape@1",
          "args": { "field": "owner_name", "normalizer": "conformed",
                    "min_tokens": 2, "max_tokens": 5, "suffix_list": "person_suffix",
                    "forbid_digits": { "value": true, "applies_to": "raw" },
                    "forbid_characters": { "value": ["&"], "applies_to": "raw" } } },
        { "primitive": "fields_all_empty@1", "args": { "fields": "structural_fields" } }
      ]
    },
    {
      "step": 2,
      "verdict": "entity_undetermined",
      "note": "Terminal for the Person consumer: retained as a deferred record, no review, no Person completeness impact.",
      "when": [
        { "primitive": "token_match@1",
          "args": { "field": "owner_name", "normalizer": "conformed",
                    "token_list": "entity_legal_form", "exclude": "ambiguous",
                    "min_count": 1 } }
      ]
    },
    {
      "step": 3,
      "verdict": "person",
      "when": [
        { "primitive": "token_match@1", "negate": true,
          "args": { "field": "owner_name", "normalizer": "conformed",
                    "token_list": "entity_legal_form", "min_count": 1 } },
        { "primitive": "fields_all_empty@1", "args": { "fields": "structural_fields" } },
        { "primitive": "name_shape@1",
          "args": { "field": "owner_name", "normalizer": "conformed",
                    "min_tokens": 2, "max_tokens": 5, "suffix_list": "person_suffix",
                    "forbid_digits": { "value": true, "applies_to": "raw" },
                    "forbid_characters": { "value": ["&"], "applies_to": "raw" } } }
      ]
    },
    {
      "step": 4,
      "verdict": "deferred",
      "note": "Steward queue. Ambiguous-token names, populated structural field with no token, non-person-shaped token-free names. ~1.1% of owners.",
      "when": []
    }
  ],
  "evidence_only": {
    "note": "Recorded on the assertion, never a decider (03:49-59).",
    "fields": ["is_officer", "is_director", "is_ten_percent_owner", "is_other",
               "officer_title", "sec.submissions.entityType", "deputization_text"]
  }
}
```

The `evidence_only` block is doing real work: it is how the document states
"Flags are evidence, never deciders" (`03:49`) and "`entityType='other'` is evidence,
never a decider" (`03:54`) **positively**, so a reader can see that the omission of
those fields from every `when` list is deliberate rather than an oversight. Whether
the interpreter validates it (refusing a `when` that names an `evidence_only` field)
is Codex's call; declaring it costs nothing either way.

Its activation entry, in research 02's shape (`research/02:107-141`) — one verdict
only, exactly as Person 03's release gates require (`03:92-97`):

```json
{
  "kind": "person", "family": "classification",
  "rule_id": "C-J", "rule_version": "2026-09-20", "verdict": "person",
  "proof": {
    "method": "wilson_lower_bound", "one_sided_confidence": 0.975,
    "n": 841, "correct": 841, "lower_bound": 0.99545,
    "cohort": { "source_codes": ["sec.ownership.reporting_owner.v1"],
                "files": { "18-sample.jsonl": "87209b16…", "18-owners.jsonl": "8181e1bf…" } },
    "approved_by": "operator:paul", "approved_at": "2026-09-20T12:00:00+00:00",
    "reason": "research 18, rule C-J person arm: 841/841, Wilson LCB 0.9955 >= 0.99"
  }
}
```

No entry exists for `verdict: "entity_undetermined"`, so step 2 runs review-only —
which is release gate 2 (`03:95-97`), expressed as an omission rather than a switch.

### Person Tier B

```json
{
  "rule_id": "person-tier-b-context-key",
  "version": "2026-09-20",
  "family": "binding",
  "kind": "person",
  "emits": ["bind"],
  "tier": "B",
  "precondition": [
    { "primitive": "field_in_set@1",
      "args": { "field": "inferred_kind", "values": ["person"] },
      "note": "Tier B keys over C-J 'person' verdicts only (03:110)." }
  ],
  "steps": [
    {
      "step": 1,
      "verdict": "bind",
      "when": [
        { "primitive": "compound_key_equal@1",
          "args": { "components": [
            { "field": "issuer_or_firm_cik",
              "normalizer": "normalize_identifier@1", "format": "sec_cik",
              "comparison": "exact" },
            { "field": "owner_name",
              "normalizer": "normalize_text@edgar-conformed-v1",
              "comparison": "exact" },
            { "field": "role_flags",
              "normalizer": "normalize_text@role-v1",
              "comparison": "consistent" }
          ] } },
        { "primitive": "identifier_cardinality@1",
          "args": { "namespaces": ["sec.owner_cik", "adv.owner_id"],
                    "max_identities_per_value": 1,
                    "on_violation": "veto_to_review" },
          "note": "Person 02 #2: a second Person claiming a bound id is a hard veto." }
      ]
    }
  ],
  "source_eligibility": {
    "note": "Which source rows may enter this tier is per-source (research 01 §5, row 18).",
    "sec.ownership.reporting_owner.v1": "eligible",
    "sec.executive_record.v1": "blocked_pending_parser_fix",
    "sec.eight_k.v1": "eligible",
    "adv.schedule_ab.v1": "eligible_identified_individuals_only"
  }
}
```

**And no `automatic_rules` entry for it.** Tier B's bar is declared once in the
Person kind section — `bars.binding.min_precision: 0.99` (`02:75`, `02:79-81`) —
but the calibration that would earn the entry is Person ticket 17, still open. Under
research 02's design that is not a special case: a rule with no activation entry
still fires, its result goes to a Steward, and the document is registrable as it
stands (`research/02:20-22`). The contrast with C-J above is the whole point of
per-`(rule_id, rule_version, verdict)` activation — one document, two rules, one
arm of one of them automatic.

For contrast, Tier A is a single predicate, which is why it needs no calibration at
all (`02:74`, "auto, deterministic"):

```json
{ "rule_id": "person-tier-a-shared-xref", "version": "2026-08-01",
  "family": "binding", "kind": "person", "emits": ["bind"],
  "steps": [ { "step": 1, "verdict": "bind", "when": [
    { "primitive": "identifier_match@1",
      "args": { "namespaces": ["sec.owner_cik", "adv.owner_id"],
                "normalizer": "normalize_identifier@1" } },
    { "primitive": "identifier_cardinality@1",
      "args": { "namespaces": ["sec.owner_cik", "adv.owner_id"],
                "max_identities_per_value": 1, "on_violation": "veto_to_review" } }
  ] } ] }
```

## 7. What could not be determined

- **Step attribution diverges from the reference implementation in one case, even
  though the verdict does not.** A person-shaped, structurally empty name whose
  single entity token is *ambiguous* (so `has_unambiguous_token` is false) reaches
  `deferred` through step `2-guard` in the encoding above, but through
  `rule_combo_h`'s terminal fallthrough (`18-classify.py:682`, i.e. step 4's
  equivalent) in `18-classify.py`. Every other case traced — ambiguous-single-token
  non-person-shaped, two-token, and populated-structural — is both verdict- and
  step-equivalent. The verdict is right either way, but Person 03:86 records "the
  step (0-4) that fired" as durable provenance and §4 exclusion 6 makes that
  load-bearing, so the prototype (ticket 04) should expect a step-label diff on
  this class in any fixture compared against `18-classify.py`, and decide which
  attribution is intended before treating it as a regression.
- **Whether `field_group_together` has any consumer at all.** It is accepted policy
  (`merge-stage.md:137-139`, `acceptance.md:42`) with no implementation in `clean/`
  and no consumer that projects addresses (`spec.md:131-138` keeps them evidence-only;
  Person's field set is Person ticket 04, open). Left out of the minimum (§3) and
  flagged to Codex as a standalone gap.
- **The publication-time tiebreak (accepted order step 4) is unimplemented.**
  `merge-stage.md:129` declares it "where the field policy permits it";
  `survivorship.py:239-249` sorts rank → effective time → stable key and never
  consults publication time. Whether that is a deliberate deferral or an oversight
  was not determined.
- **What "consistent role/flag" means in Tier B.** `02:75` states it; nothing defines
  whether "consistent" means identical flag sets, non-contradictory ones, or normalized
  titles (the legacy `title_alias` seeds at `002_seed_data.sql:104-131` are the only
  role-normalization artifact in the repo). `compound_key_equal`'s `comparison:
  "consistent"` is a placeholder until Person ticket 17 defines it.
- **The `identifier_cardinality` "one value per identity" direction has no
  implementation.** `identity.py:73-76` enforces one identity per subject; the GLEIF
  rule needs both directions (`spec.md:97`) and the cross-namespace case (a CIK and an
  `OwnerID` disagreeing, `02:21`) has none.
- **How Splink versions its comparison functions** was not checked. The sibling
  research surveyed Splink twice for scoping and activation
  (`research/01:198`, `research/02:310`) and found it has no survivorship and no
  activation concept; the in-repo answer to versioning is `merge-stage.md:66-70`, so no
  vendor fetch was made for this ticket. If Codex wants an external precedent for
  pinning a similarity implementation, Splink's model-serialization page is the place
  to look — this research does not claim what it says.
- **`ml_splink` is excluded deliberately.** It has a legacy threshold seed
  (`002_seed_data.sql:66`) and a code hook (`match.py:163-193`), but the model is
  injected at construction and trained elsewhere (`match.py:166-171`); nothing in the
  repo shows it trained or run. A model-scored primitive would also break the purity
  contract in §2 (its behaviour lives in a model artifact, not in `name@version`), so
  it needs its own decision, not a table row.
- **Whether blocking/candidate generation is needed at production scale.** Person `#3`
  requires an exhaustive attempt (`02:67-68`); §3 argues a blocking key out of the
  vocabulary on recall-measurement grounds, but no scale test was run to say whether
  exhaustive comparison is actually tractable for the Person universe.
- **GLEIF's revalidation triggers are not modelled.** `spec.md:100-104` lists seven
  (changed LEI record, changed mapping, conflicting candidate, successor/duplicate/
  retired status, monthly reconciliation, rule-version change). These are *scheduling*
  and lifecycle conditions — when to re-run a rule — not predicates a rule evaluates,
  so they belong to the map's unspecified "Change and replay" item, not to this
  vocabulary.
- **Where the classification rules live** (`mdm_v2.policy.body` vs
  `mdm_v2.dataset.body.adapter`) is still research 01's open "Authoring surface"
  item (`research/01:283-290`); §6 shows the vocabulary is unaffected either way but
  does not settle the home.
