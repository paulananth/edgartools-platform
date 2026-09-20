# Research 07: the `owner_cik` cardinality claim, measured, and deterministic binding run for real

Ticket: [07](../issues/07-measure-owner-cik-cardinality-and-test-deterministic-binding.md).
Map: [Mastering Policy Language](../map.md). Feeds ticket 06 Q2. Date: 2026-09-20.
**Everything here is throwaway**: the scripts, the copied interpreter, the result JSON.
Bronze only (prod S3, account `690839588395`, `us-east-1`); no Snowflake; zero SEC requests.
Labels are my own reading, as research 18's were; every uncertain one is marked in the
labelled sample file.

## The paragraph

The claim "one `owner_cik` → one Person" holds on every row we have: across 104,970 Form 3/4/5
reporting-owner rows (21,727 distinct CIKs, both bronze corpora combined) I found **zero** CIKs
carrying two different people. 42 CIKs carry two names, and all 42 are the same person or entity
under a name variant, typo, nickname, legal name change, or corporate rename — and the SEC's own
spec explains why nothing worse can appear: a filer *cannot* set the owner name on a Form 3/4/5;
EDGAR discards it and inserts the name registered to the CIK (EDGAR Ownership XML Technical
Specification v5.1 §4.3.2). So the forward direction measures registered-name changes, not
typing, and its true violation rate is 0 per 10,000 with a 95% upper bound of 0.5 per 10,000
binding decisions. The reverse direction is equally clean where it matters: no person name
appears under two CIKs at the same issuer (0 of 16,677 pairs; CRD `OwnerID` runs at ~12 per
10,000 on the same test, research 16), and the 6 name-only collisions are homonyms at different
issuers. Running the deterministic rule for real changes the question: the runtime can only
*detect* a violation through a second handle (the name), so what it sees is not the true rate
but a name-mismatch alarm rate — 21 per 10,000 records if any spelling difference counts, 8 if
only unexplained ones do, and every one of them a false alarm. Option (b), deactivate on first
violation, shut the rule down at decision 3,107 of 72,981 on a middle initial and sent 96% of the
corpus to the Steward. Option (c) never trips on real data once it counts distinct items rather
than records, waits 10,000 decisions, and sits at ≥ 5 items per 10,000 — and under a synthetic
bulk failure (2,000 rows with the wrong identifier) it stopped the rule within 8–48 decisions,
where option (a) silently minted 291 bogus Persons because a wrong id that happens to be unbound
never collides with anything. Honest summary for Q2: the measured tolerance is "effectively
zero" for true violations, (c) is a circuit breaker for a *broken contract*, not for the data
we have, and it only works with four tuning knobs (predicate, unit, warm-up, threshold) that
(a) does not need. (a) is sufficient for the data; (c) is insurance against a source or parser
regression, and the data cannot tell you how much that insurance is worth.

## Sources read

Primary data (S3 bucket `edgartools-prod-bronze-690839588395`, prefix `warehouse/bronze/`; all
synced to the session scratchpad by research 18 on 2026-09-20 and reused unchanged):

- `filing_artifact/<sha256>` — 5,356 full `.txt` submissions → the **primary corpus**,
  `.scratch/person-consumer-contract/research/18-owners.jsonl` (5,743 rows, SHA-256
  `8181e1bf…19ff1c`), already joined to submissions by research 18's `parse` stage.
- `filings/sec/cik=<cik>/accession=<acc>/primary/*.xml` — 114,595 keys, saved as 112,490
  accession-named files (`r18/fetch_primaries.py` names the file by accession, so 2,105 keys
  under an already-seen accession collapsed); 91,110 are `<ownershipDocument>` → the **legacy
  corpus**, `r18/legacy_rows.jsonl` (101,137 rows, SHA-256 `c00b0351…89fec1`), parsed by
  `18-classify.py:196-278` (`parse_artifact`) via its `extend` stage (`:886-940`), which does
  **not** join submissions.
- `submissions/sec/cik=<cik>/main/<yyyy>/<mm>/<dd>/CIK<10>.json` — newest `main` object per
  CIK. Research 18 had 6,854; this ticket pulled 11,102 more for the legacy owner CIKs
  (`r07/fetch_subs_legacy.py`, same latest-per-CIK pick as `r18/fetch_subs.py`; 0 errors).
  **5,607 of 19,735 legacy owner CIKs have no submissions object in bronze at all.**

Specification: EDGAR Ownership XML Technical Specification, Version 5.1, September 2015
(`scratchpad/ownspec.txt`, extracted from the PDF research 15 downloaded), §4.3.2 "Specifying a
Reporting Owner", lines 1228-1234:

> Do not provide a Reporting Owner Name. EDGAR will insert the Owner Name associated with the
> provided CIK into the "document of record" that get disseminated. If you do include a value
> for the `<rptOwnerName>` element, EDGAR will issue a WARNING and discard the provided value.

Repo code: `18-classify.py:120-125` (`norm_name`), `:139-150` (`person_name_shape`),
`:302-342` (`load_submission`), `:356-369` (the submissions join), `:435` (corpus order key),
`:697-706` (`rule_combo_j`), `:737-744` (`wilson`, two-sided z = 1.959964 — the same z as the
one-sided 97.5% the policy bars declare, `policy-person.json:8,12`, `interpret.mjs:156`);
`prototype/interpret.mjs:91-92` (the stubs), `prototype/policy-person.json:367-394` (the rule,
`max_identities: 1` at `:390`); ticket 02's Answer (`person-consumer-contract/issues/02-*.md:56-66`:
a Person holds any number of cross-reference ids; a second *Person* claiming a bound id is the
veto); research 16 (`16-schedule-ab-ownerid-meaning.md:183-209`) for the `OwnerID` comparison.

Sibling files (this directory): `07-measure.py` (part 1), `07-cardinality.json` (its output,
with input hashes), `07-labelled-sample.jsonl` (every multi-name CIK and every reverse collision
in the union, with my label and reason), `07-run-binding.mjs` (part 2),
`07-binding-results.json` (its output), and `../prototype/interpret-binding.mjs` (the copy of
`interpret.mjs` with real binding primitives; `interpret.mjs` and `run-check.mjs` are unmodified
vs HEAD, and `node run-check.mjs` was re-run in full after the copy was made: person 841/841,
entity 353/353, 26 deferred, unchanged).

**Not retained:** the binding run's input, `r07/07-union-corpus.jsonl` (the union with C-J
verdicts attached, in `(accession, owner_index)` order), lives only in the session scratchpad,
as the ticket requires. Both result JSONs cite it by absolute path and by SHA-256
(`9daf08fb0101…`, identical in both). It is regenerated by re-running `07-measure.py` against a
re-synced `r18/` cache (research 18's `fetch_primaries.py` / `fetch_subs.py` plus this ticket's
`fetch_subs_legacy.py` for the 11,102 extra submissions objects).

## Part 1 — the claim, measured

### Method

`07-measure.py` loads both corpora, joins the legacy rows to submissions exactly as
`stage_parse` does (`07-measure.py:189-213`), classifies every row with research 18's own
`rule_combo_j` (imported, not re-implemented), builds the union deduplicated on
`(accession, owner_index)` (1,910 duplicates dropped, legacy first), and for each of
primary / legacy / union, unrestricted and restricted to C-J `person` rows, counts:

- **forward**: distinct `norm_name` per `owner_cik`;
- **reverse**: distinct `owner_cik` per `norm_name` and per `(issuer_cik, norm_name)`.

Every multi-name CIK is pre-sorted automatically into a name-relation class
(`07-measure.py:120-162`: identical → subset/initial/nickname variant → reorder/middle →
typo/prefix → suffix differs → one shared token → no overlap → entity-vs-person name), then
**every one** (42 forward, 10 reverse) was read by hand with its per-name row counts, issuers,
`submissions.json` name and address, and the order of its filings. Rates are per 10,000 with
Wilson 95% intervals, in two denominators: rows (= binding decisions, what a runtime tolerance
would count) and distinct CIKs (what the claim is about).

C-J verdicts entering the person-restricted numbers: primary 5,145 person / 530 entity / 68
deferred; legacy 69,515 / 8,936 / 22,686 deferred (21,539 of those deferred rows are the
5,607 CIKs with no bronze submissions — C-J's step 0, a coverage limit, not a finding); union
72,981 / 9,254 / 22,735.

### The fact that reframes the forward direction

The spec passage above is corroborated by the data three ways: (i) in the primary corpus,
`rptOwnerName` equals the SGML header's `COMPANY CONFORMED NAME` for the owner in **5,743 of
5,743** rows and equals the CIK's `submissions.json` `name` in 5,742 (the exception is an
entity, CIK 1569064, later renamed); (ii) no CIK anywhere carries more than **two** names
(41 of the 42 two-name CIKs switch name exactly once when their filings are ordered by period
— the shape of a registered name change, not of free text); (iii) the 11-day primary window
has zero two-name CIKs and the multi-year legacy corpus has 41. 99.6% of union rows have a
`periodOfReport` in 2023 or later, well after the spec version that documents this behaviour.

Consequence: a `rptOwnerName` difference on one CIK is a **registered** event on the filer's
EDGAR account. A CIK can only "become a different person" if the SEC re-registers the account
to someone else — which is what would have to be true for a genuine violation.

### Forward direction: names per `owner_cik`

| corpus | rows | CIKs | CIKs with 2 names (3+: none) | rows under them | rows with the non-majority name | genuinely different person (labelled) |
|---|---|---|---|---|---|---|
| primary, all | 5,743 | 4,831 | 0 | 0 | 0 | 0 |
| primary, C-J person | 5,145 | 4,426 | 0 | 0 | 0 | 0 |
| legacy, all | 101,137 | 19,735 | 41 | 423 | 117 | 0 |
| legacy, C-J person | 69,515 | 12,658 | 25 | 256 | 74 | 0 |
| **union, all** | 104,970 | 21,727 | 42 | 437 | 119 | **0** |
| **union, C-J person** | 72,981 | 14,566 | 26 | 269 | 75 | **0** |

Reason classification of the 42 union multi-name CIKs (all 42 read, `07-labelled-sample.jsonl`;
the 26 in the person subset are a strict subset of these):

| label | all 42 | in C-J person 26 | examples |
|---|---|---|---|
| name variant (middle initial/name added or dropped, token reorder, second surname) | 19 | 13 | `Kissner Matthew` / `KISSNER MATTHEW S`; `GIBSON SCOTT C` / `GIBSON C SCOTT`; `Zamora Javier Esquivel` / `Zamora Javier` |
| legal name change, given name kept, same issuer, one switch in time | 8 | 5 | `Gottung Lizanne C` → `Bruce Lizanne M`; `Sandoval Elisabeth` → `Little Elisabeth Sandoval`; `Bateman Jessica Walker` → `Pulliam Jessica Bateman` |
| nickname | 4 | 4 | `Porcelli Francis Michael` / `Porcelli Frank`; `BALLARD CHARLES ANDREW` / `BALLARD ANDY` |
| typo corrected on the account | 3 | 3 | `Corrreia` / `Correia`; `Paranksy` / `Paransky`; `Vavilovs Valerijis` / `Valerijs` |
| suffix dropped | 1 | 1 | `Meyer Robert Joseph JR` → `Meyer Robert Joseph` — same officer at the same issuer, continuous 2024-2026 |
| entity renamed on its CIK (not person-classified) | 7 | 0 | `EOS Technology Holdings Inc.` → `Data Vault Holdings Inc.`; `GA AL Holding, L.P.` / `General Atlantic Partners (Bermuda) T, L.P.` |
| **genuinely different person** | **0** | **0** | — |

Six labels are marked `uncertain` (the four marriage-type changes and two reverse homonyms whose
second CIK has no submissions); none has evidence pointing at a different person — every
name-change case keeps the given name, the issuer and the role, and switches once.

Rates (Wilson 95%):

| quantity | k / n | per 10,000 | 95% interval |
|---|---|---|---|
| true violations, union person **rows** (= binding decisions) | 0 / 72,981 | 0 | [0, 0.53] |
| true violations, union person **CIKs** | 0 / 14,566 | 0 | [0, 2.64] |
| true violations, union all rows | 0 / 104,970 | 0 | [0, 0.37] |
| any second name, union person CIKs | 26 / 14,566 | 17.9 | [12.2, 26.1] |
| any second name, union person rows carrying the non-majority name | 75 / 72,981 | 10.3 | [8.2, 12.9] |
| pre-sort "candidate different person" classes before reading (all resolved as typo/name change on inspection) | 6 / 72,981 | 0.82 | [0.38, 1.79] |

### Reverse direction: CIKs per name

| corpus (C-J person rows) | distinct names | names with 2 CIKs | (issuer, name) pairs | pairs with 2 CIKs |
|---|---|---|---|---|
| primary | 4,425 | 1 | 4,576 | 0 |
| legacy | 12,680 | 3 | 14,513 | 0 |
| **union** | 14,586 | 6 | 16,677 | **0** |
| union, all rows (incl. entities) | 21,759 | 10 | 24,944 | 2 |

All 10 union collisions read (`07-labelled-sample.jsonl`, direction `reverse`):

- The **2 same-issuer pairs are entities** with two SEC accounts, not people: `GOLDMAN SACHS &
  CO. LLC` under CIKs 42352 and 769993 (both `submissions.json` names identical, two addresses),
  and `Imperial Capital Asset Management, LLC` under 1805378 and 2047704. That is the Company
  kind's Identity Consolidation load, outside this rule.
- The **8 name-only collisions are homonyms**: every pair sits at different issuers with
  different mailing addresses in `submissions.json` (`BARBER JAMES J` c/o Metabolix vs 55
  Glenlake Pkwy; `O CONNOR KEVIN J` c/o DoubleClick vs Rockledge Dr; `JOHNSON STEPHEN L`,
  `CARROLL JOHN A`, `JACKSON BENJAMIN`, `SINGH MOHIT`, `ZHANG SHUO`, `ZHANG WEI`). None is a
  duplicate account of one person as far as bronze can tell.

| quantity | k / n | per 10,000 | 95% interval |
|---|---|---|---|
| same person, two CIKs, same issuer (duplicate account — the Identity Consolidation case) | 0 / 16,677 | 0 | [0, 2.30] |
| name-only collision, person rows (homonyms, Tier C territory) | 6 / 14,586 | 4.1 | [1.9, 9.0] |
| research 16, CRD `OwnerID`: same firm, identical full name, two ids | 9 / 7,618 | 11.8 | [6.2, 22.4] |
| research 16, CRD `OwnerID`: one id, two different surnames | 2 / 7,060 | 2.8 | [0.8, 10.3] |

So `owner_cik` behaves as an account credential — one CIK, one CCC, one registered name — and is
cleaner than `OwnerID` in the direction where `OwnerID` was found wanting (research 16: 2 of 5
probed same-name pairs were IAPD-confirmed as one person with two records). The Person
document's two Tier A rules therefore rest on different contracts: `sec.cik` can declare
"one value → one Person" with a measured zero; `crd.individual` cannot, and its rule
(`policy-person.json:395-415`) rightly carries no `identifier_cardinality` call.

## Part 2 — deterministic binding, run for real

### What "violation" can even mean at runtime

Binding by `owner_cik` alone never contradicts itself. The claim `max_identities: 1` is only
testable if a Person has a second handle; the only one in the source is the name. So
`identifier_cardinality@1` in the copy (`interpret-binding.mjs:118-133`) compares the incoming
record's name with the names already on the Person the CIK resolves to
(`IdentityStore.worstRelation`, `:339-357`), and a "materially new" name is the candidate
violation. That is a heuristic inside a deterministic rule, and it is the thing the ticket 06
options are really arguing about. Two predicates were run as a switch:

- **strict** — any non-identical normalized name;
- **lenient** — only relations the part-1 pre-sort could not explain (`LENIENT_INCOMPATIBLE`,
  `:292`: suffix differs, one shared token, near-token, entity-vs-person, no overlap).

The reverse direction (a Person would acquire a second CIK: same `(issuer, name)` already bound
under another CIK) is detected and reported (`consolidationCandidates`, `:358`) but never
vetoed — ticket 02's Answer #1 says a Person holds any number of cross-reference ids. It fired
**0** times on the person rows (matches part 1). Name-only homonyms fired 6 times (the same 6).

`identifier_match@1` (`:106-116`) normalizes with `normalize_identifier@sec-cik-v1` and looks
the value up in the store; an unbound id still matches (creation is the last outcome after
matching, ticket 02 Answer #3) and `bind` creates the Person (`:375-389`). Input: the 72,981
C-J `person` rows of the union, in `(accession, owner_index)` order (research 18's key) with a
`(period, accession, owner_index)` order as a chronological sensitivity check. The JS port of
the pre-sort reproduces the Python classes exactly (16 / 5 / 3 / 1 / 1 on the 26 person CIKs).

### The three behaviours, naive settings (`07-run-binding.mjs`, `results.runs`)

Tolerance for (c) counted violating **records** per 10,000 decisions, cumulative, evaluated
after 1,000 decisions. Accession order:

| option | predicate | bound | deferred (violation) | deferred (rule inactive) | alarm rate /10k | Steward items (distinct CIK+name) | deactivated |
|---|---|---|---|---|---|---|---|
| (a) defer record | strict | 72,830 | 151 | 0 | 20.7 | 26 | never |
| (a) defer record | lenient | 72,925 | 56 | 0 | 7.7 | 7 | never |
| (b) deactivate on first | strict | 3,106 | 1 | **69,874** | — | 1 | decision 3,107: `Kissner Matthew` vs `KISSNER MATTHEW S` |
| (b) deactivate on first | lenient | 3,820 | 1 | **69,160** | — | 1 | decision 3,821: `Corrreia` / `Correia` |
| (c) tol 0.5–2 | either | ≤ 3,820 | 1 | ≥ 69,160 | — | 1 | same first event as (b): one record at n≈3,100 is already 3.2/10k |
| (c) tol 5 | either | ~3,830 | 2 | ~69,150 | — | 1 | decision 3,140 / 3,830 |
| (c) tol 10 | strict / lenient | 3,817 / 3,843 | 4 / 4 | 69,160 / 69,134 | — | 2 / 1 | decision 3,821 / 3,847 |
| (c) tol 20 | strict | 15,341 | 31 | 57,609 | — | 10 | decision 15,372: the 27-record `Vavilovs` typo item pushes the cumulative rate over 20 |
| (c) tol 20 | lenient | 72,925 | 56 | 0 | 7.7 | 7 | never |

Period order gives the same picture with different trip points (strict alarm rate 22.5/10k,
lenient 10.6/10k; (b) trips at decision 5,582). Alarm-rate intervals: strict records
20.7 [17.6, 24.3], lenient 7.7 [5.9, 10.0]; as distinct items strict 3.6 [2.4, 5.2], lenient
0.96 [0.47, 1.98] per 10,000 decisions.

**What the Steward queue holds under (a), lenient, accession order** (7 items, 56 records):
`Corrreia Christina` → `Correia Christina` (6 records), `Meyer Robert Joseph JR` →
`Meyer Robert Joseph` (4), `Vavilovs Valerijis` → `Vavilovs Valerijs` (27 — the typo'd name
was registered first in this order, so the 27 *correct* filings are the ones deferred),
`Gottung Lizanne C` → `Bruce Lizanne M` (4), `Paranksy Noam` → `Paransky Noam` (8),
`Hurse Sandra` → `Buchanan Sandra M` (1), `Amara Carmen` → `Orr Carmen` (6). Under strict, add
19 middle-initial/reorder items. Every item is an alias the Steward would confirm; each recurs
on every later filing until the alias is recorded, which is why one prolific filer looks like a
burst to a record-counting tolerance. Violations are scattered: 26 CIKs across 28 issuers,
present in all ten deciles of corpus order (strict: 7, 15, 29, 22, 24, 9, 17, 13, 3, 12).

### (c) tuned: count items, warm up longer (`results.tuned`)

Counting distinct `(cik, incoming name)` items instead of records, evaluating only after
10,000 decisions, cumulative and 10,000-decision window, both orders:

| predicate | tolerance (items/10k) | accession order | period order |
|---|---|---|---|
| strict | 1, 2 | trips at ~11,450 (5 items = 4.4/10k) | trips at ~11,410 |
| strict | 5 | trips at 11,520 (cumulative and window) | cumulative never; window trips at 28,619 |
| strict | 10, 20 | **never** | **never** |
| lenient | 1 | trips at 14,467 (cumulative) / 14,838 (window) | trips at 11,410 |
| lenient | 2 | cumulative trips at 14,838; window never | trips at 11,410 |
| lenient | 5, 10, 20 | **never** | **never** |

The early trips are small-n arithmetic (4–5 items at n ≈ 11,000 is 4/10k even though the
whole-corpus item rate is 3.6 strict / 0.96 lenient); the tolerance has to clear the
detector's *early* alarm rate, not its asymptotic one.

### Does (a) miss a pattern (c) catches? A synthetic broken contract (`results.injection`)

Rows 40,000–41,999 of the person corpus (accession order) were given `owner_cik :=
issuer_cik` — the shape of a mis-mapped identifier column or parser regression. What each
option let through, injected rows only:

| option | bound silently | bogus Persons created | deferred as violation | deferred (rule inactive) | when it stopped |
|---|---|---|---|---|---|
| (a) defer record, strict | **784** | **291** | 1,216 | 0 | never |
| (a) defer record, lenient | 788 | 291 | 1,212 | 0 | never |
| (b), any | 0 | 0 | 0 | 2,000 | — but only because it had already died at decision 3,107 / 3,821 on real-data noise |
| (c) naive tol 5–20, records | 0 | 0 | 0 | 2,000 | same: already dead before decision 40,000, except lenient tol 20 (below) |
| (c) lenient tol 20, records, cumulative | 35 | 30 | 42 | 1,923 | decision 40,077 — 77 into the burst |
| (c) lenient tol 2, items, window | 5 | 5 | 3 | 1,992 | decision 40,008 |
| (c) lenient tol 5, items, window | 15 | 14 | 6 | 1,979 | decision 40,021 |
| (c) lenient tol 5, items, cumulative | 30 | 25 | 18 | 1,952 | decision 40,048 |

The mechanism (a) cannot see: 39% of the wrong ids were **unbound** at the time, so they
matched nothing, collided with nothing, and created a Person each — a clean-looking bind. Only
the 61% that hit an already-bound issuer CIK raised a violation, and (a) by construction treats
each as an isolated record. Its Steward queue would have shown 1,216 items in a burst — a human
would notice — but nothing automatic stops the rule. A tuned (c) stopped it within 8–48
decisions at the cost of 5–30 bogus Persons instead of 291.

## Plain answers

**What tolerance does the measured rate imply?** For *true* violations, effectively zero: 0 in
72,981 person decisions (upper bound 0.53 per 10,000) and 0 in 14,566 CIKs (upper 2.6 per
10,000), with the SEC spec explaining why — the name is EDGAR's, not the filer's. A tolerance
written against that rate would be < 1 per 10,000 and would be tripped by the detector, not
the data. The number a runtime tolerance actually has to clear is the **name-mismatch alarm
rate** of whatever predicate detects the violation: ≈ 21 records or 3.6 items per 10,000 for
any spelling difference, ≈ 8 records or 1 item per 10,000 for unexplained differences. If (c)
is adopted, the evidence supports **≥ 5 distinct items per 10,000 decisions, lenient predicate,
evaluated after ≥ 10,000 decisions** (≥ 10 for the strict predicate) — those survived both
orders of the real corpus and still caught the synthetic bulk failure within tens of
decisions. The interval width matters: the lenient item rate is [0.47, 1.98] per 10,000, so 5
is ~2.5× the upper bound — comfortable, not tight.

**Does (c) ever trip on real data, or only in theory?** On the real corpus it trips only when
mis-tuned: on a middle initial at decision 3,107 with a record-counting tolerance, on one
filer's 27 typo'd filings with a 10,000-record window. With items, warm-up and a tolerance at
or above 5 (lenient) it **never** tripped in 72,981 decisions in either order, because there is
nothing in the data to trip on. It trips in theory — against a broken identifier contract —
and the injection shows that it does so quickly when it is still alive to see it.

**Would (a) have missed a pattern (c) catches?** On real data, no: the alarms are 26 scattered
alias events across 28 issuers with no clustering by CIK, issuer or time; (a) queues each once
per record and a Steward confirms an alias. Under a bulk identifier failure, yes: (a) silently
minted 291 wrong Persons out of 2,000 wrong rows because unbound wrong ids never collide, and
only the rule-level breaker stopped that. But (b) is not that breaker — it died on the first
middle initial at 4% of the corpus and sent the other 96% to the Steward — and (c) is only that
breaker with four declared knobs (predicate, unit, warm-up, threshold), which is exactly the
moving-parts cost ticket 06 asked about. The data supports (a) as sufficient for the claim as
it holds today, and supports (c) only as insurance whose premium the data cannot price.

## Findings for the spec (tickets 05 and 06)

1. **A deterministic rule's cardinality veto is not deterministic.** It needs a second handle
   (the name) and a compatibility predicate on it; the spec must declare that predicate, its
   version, **and the field it compares** alongside `identifier_cardinality`, or the veto is
   unreplayable. The prototype shows the gap concretely: the copy reaches for `owner_name`
   as a literal (`interpret-binding.mjs:124`) because nothing in the rule's `args`
   (`policy-person.json:387-391`) names the field.
2. **The identifier contract for `sec.cik` can be stated with its evidence**: issuing
   authority SEC/EDGAR; the name is EDGAR-inserted (spec v5.1 §4.3.2), so a name difference on
   one CIK is a registered account event; measured 0 / 72,981 decisions, upper bound 0.53 per
   10,000; reverse 0 / 16,677 same-issuer pairs. This is the "measured verification that the
   claim holds on the corpus" that Q1's answer requires.
3. **`crd.individual` cannot make the same claim** (research 16: 11.8 per 10,000 same-firm
   same-name pairs with two ids), which is why its Tier A rule declares no cardinality — the
   two rules differ in contract, not just in namespace.
4. **If (c) is chosen, count distinct `(identifier, incoming name)` items, not records**, and
   declare a warm-up; otherwise one prolific filer with one typo'd registered name is a burst.
5. **A Steward resolution must record the alias**, or the same item recurs on every later
   filing (27 records for one typo here). The queue contents under (a) are alias confirmations,
   not identity decisions.

## What could not be determined

- Whether any of the 6 `uncertain` labels is wrong: 4 marriage-type name changes and 2
  homonyms whose second CIK has no bronze submissions. No SEC or IAPD request was allowed;
  the same-issuer / same-role / single-switch evidence points one way, but it is my reading.
- The forward rate on the **5,607 legacy owner CIKs (21,539 rows) with no submissions in
  bronze**: C-J defers them at step 0, so they are outside the person-restricted numbers. The
  unrestricted numbers include them and show the same shape (42 vs 26 two-name CIKs, 0
  genuine) — but a person there is classified by nobody.
- A genuinely different person with a *compatible* name (father and son with no suffix on
  the account, or a re-registered account keeping the surname) is invisible to both the
  measurement and the runner. The spec fact says the account would have to be re-registered;
  how often EDGAR does that was not measurable from bronze.
- Whether EDGAR inserted the name in filings before the spec version I read (v5.1, Sept
  2015). 99.6% of union rows are 2023 or later; the 1987–2013 rows are 23 in total and none
  is a two-name CIK.
- 2,105 legacy S3 keys collapsed onto already-seen accession filenames in research 18's
  download and were not re-examined here.
- The injection is one failure shape (issuer CIK in the owner slot, 2,000 contiguous rows).
  A slow drift (a few wrong ids per day) would look exactly like the alias noise to every
  option, and no tolerance tested here separates them.
- How much a bulk failure like the injected one costs in production, which is what would
  price (c)'s insurance. Not a data question this corpus can answer.
