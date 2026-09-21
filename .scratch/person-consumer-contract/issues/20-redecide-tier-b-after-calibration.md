# Re-decide Tier B now that it has been measured

Type: grilling
Status: resolved 2026-09-20
Blocked by: none (17 resolved 2026-09-20)

## Answer

Tier B, as ticket 02 §4 defined it, is replaced by this. Four decisions:

**1. Identifiers veto, everywhere.** If two records carry identifiers in
the same namespace and the values differ, the pair is vetoed — never
auto-merged, never queued for review one at a time — and recorded as a
counted `distinct_identified` disposition. Stated as a reason (an
identifier in a namespace whose Identifier Contract declares exclusivity
is a distinguishing fact), so it lives in the Mastering Policy rather
than as a per-source exception. Effect today: Tier B fires only where no
identifier exists — 8-K now, DEF 14A after ticket 10 — because ADV
carries `OwnerID` on 99.7% of rows and Form 3/4/5 carries `owner_cik` on
100%, and their residual is 27 different to 1 same.

**2. The bar is ≥ 99% precision at a one-sided 97.5% Wilson lower
bound**, replacing ticket 02's 95%. Tier B does **not** activate on the
current measurement (8-K `mi`: LCB95 0.98801, LCB97.5 0.98307, and the
pooled optimistic reading rests on 8 unsettled pairs). 8-K stays Tier C
until [ticket 21](21-extend-tier-b-labelling-to-97-5.md) measures n ≥ 381.
One bar, matching research 18's method, so the Person amendment to Codex
no longer ships two.

**3. The key** is: same **MDM-resolved** issuer/firm identity + surname,
given name and **middle initial** (an initial matches a middle name;
absent-on-both matches) + **no generational-suffix conflict** (suffix on
one side only is a conflict — a hard veto, not a normalization step).
**Role and flags are evidence, never key.** Pure equality plus one veto;
no `name_similarity`.

**4. DEF 14A is measured but not counted** toward activation while 58.7%
of its `exec_name` values are role text; it activates on its own n after
ticket 10 and a re-export.

**Standing principle (operator, 2026-09-20)**: all sources resolve every
entity they carry through MDM — id resolution, de-duplication, merging.
No local or derived identity keys anywhere.

Consequences: ticket 21 charted (8-K labelling to n ≥ 381); ticket 02 §4
superseded; the Person Q11 amendment to Codex is restated at 97.5% with
the identifier veto added.

## Grilling log

**Q1 — does Tier B still apply to id-bearing sources (2026-09-20).**
**(b) yes, with a same-namespace identifier veto.** If both records carry
identifiers in the same namespace and the values differ, the pair is
vetoed — never auto-merged — and recorded as a counted
`distinct_identified` disposition rather than sent to review one at a
time. The veto is stated as a *reason* (an identifier in a namespace
whose Identifier Contract says one id means one person is a
distinguishing fact) rather than as a source list, so it lives in the
Mastering Policy's Identifier Contract where exclusivity is already
declared per namespace, and the next source inherits it. On today's data
it vetoes all 55 ADV residual pairs (27 different, 1 same, 27 unsettled)
and leaves Tier B firing only where no identifier exists: 8-K now, DEF
14A once [ticket 10](10-fix-proxy-executive-name-parser-leak.md) lands.

**Operator principle, stated with Q1 (2026-09-20).** *"All sources must
use MDM to resolve any entity they carry; every entity must go through id
resolution, de-duplication and merging."* No source keeps a local or
derived identity key, and no consumer invents one. Named consequences in
this repo: gold's owner key is a hash of `'cik:' || owner_cik` else
`'name:' || owner_name_norm` (`ownership_holdings.sql:63-67`) and must
become the MDM Person id; legacy's per-issuer name stubs (research 12,
13) are not carried forward; issuers, ADV firms, securities and funds
referenced by a Person source resolve through MDM as well, which is
exactly why ticket 05 Q7 defers an edge whose far endpoint is not yet an
accepted identity instead of publishing a local key.

**Q2 — confidence level and reading (2026-09-20).** **(a) one-sided
97.5%, after a second labelling pass.** Tier B does not activate on the
current measurement: pooled name-only at `mi` is LCB95 0.99033 (clears
99%) but LCB97.5 0.98632 (does not), and the whole optimistic reading
rests on 8 unsettled pairs — counted as errors it falls to 0.9495.
Research 17 says the pairs that would settle it exist offline: 721 8-K
and 626 DEF 14A rows have a same-issuer Form 3/4/5 anchor and only 213
were labelled, so ~104 more clears the 97.5% n (≥ 381). Chartered as
[ticket 21](21-extend-tier-b-labelling-to-97-5.md). Until it passes,
8-K binds at Tier C (Steward review) — where it sits today, so nothing
regresses. Choosing 97.5% also removes the mismatch the Mastering Policy
spec flags for Codex (§13) and matches research 18's method, so the
Person amendment asks for **one** bar: ≥ 99% precision at a one-sided
97.5% Wilson lower bound.

**Q3 — the key's exact definition (2026-09-20).** **(a) adopt all three
of research 17's changes.** The Tier B key is:

1. **same issuer/firm identity** (an MDM-resolved identity, per the Q1
   principle — not a raw CIK or CRD string), **and**
2. **surname + given name + middle initial** (`mi`): a middle initial
   matches a middle name; absent-on-both matches. `full` (exact middle
   name) misses all 84 known-same name-variant pairs; `fl` (first initial
   only) is where contradictions start and father/son clusters collapse
   (research 17 F2, F4), **and**
3. **no generational-suffix conflict** — `JR`/`SR`/`II`/`III`/`IV`
   present on one side only is a **conflict**, not a match. 11 of 166
   homonym pairs are a father/son separated by nothing else, 9 of them
   suffix-on-one-side-only (F3). This is a **hard veto**, not a
   normalization step.

**Role and flags are evidence, never key** (F6): requiring role
consistency would reject 33 same-person pairs — the CEO later seated on
the board — and catch 10 ADV pairs the name already catches. That also
keeps ticket 05's `capacity` on the relationship rather than in identity
resolution. The key is pure equality plus one veto: no
`name_similarity`, expressible in the Mastering Policy's existing
primitives.

**Q4 — DEF 14A's place in the bar (2026-09-20).** **(a) measure it, do
not count it.** The activating measurement is **8-K only**; DEF 14A's 51
labelled pairs stay in the record as corroboration, not as activation
evidence, because they were drawn from the 41% of rows that are actually
names — **58.7% of `exec_name` values are role text**, not people
(`edgar/proxy/html_extractor.py:857-864` copied at
`proxy_fundamentals.py:108`; ticket 10). Activation evidence must come
from the population the rule will run on, and a 41%-clean source
filtered to its clean part is not that population: `"Executive Officer"`
at two issuers reads to the key as one person with two employers.

Excluding it costs nothing now — ticket 02 §6 already bars proxy rows
from every tier until ticket 10 lands. It is temporary: after the parser
fix and a re-export, DEF 14A is re-measured on its own n against the
same 97.5% bar and activates on its own evidence, likely better than
8-K's, since its names are tabular rather than reconstructed from prose
by a dependency parse (research 13 F5). What DEF 14A is worth keeping
for: it is the richest tenure source in scope — one row per named
executive officer per fiscal year, so consecutive years give observed
`roles[]` intervals — and the only source naming executives who never
trade and whose appointment predates the 8-K window.

Consequence for [ticket 21](21-extend-tier-b-labelling-to-97-5.md): its
labelling target is **8-K only**, which needs n ≥ 381 against 223 today
(721 8-K rows have a same-issuer Form 3/4/5 anchor available).

## Question

[Research 17](../research/17-tier-b-context-key-calibration.md) measured
ticket 02's Tier B key on 921 labelled pairs and found its stated home and
its measured home are opposite. Ticket 02 stands except where this ticket
amends it; four things need an operator decision:

1. **Scope.** Tier B is defined for "a record whose cross-reference ids are
   all unbound" — true for ~0.3% of ADV rows and 0% of Form 3/4/5 rows.
   On id-bearing sources the residual it decides is **1 same / 27 different**
   (precision 0.018). Does Tier B stop applying to id-bearing sources
   altogether (same name + same firm + *different* ids ⇒ Tier C or an
   explicit "different person" prior), or keep applying with a veto?
2. **The bar.** Pooled name-only (8-K + DEF 14A), `mi` variant: 269/269 with
   8 unsettled, **LCB95 0.99033 — clears 99%**; LCB97.5 0.98632 — does not.
   The Mastering Policy spec already flags this 95%/97.5% mismatch as an
   item for Codex. Accept at one-sided 95% and ship, or label the 104
   further pairs research 17 says exist and clear 97.5% too?
3. **The key's fields.** Research 17 says: drop "consistent role/flag" from
   the key (it rejects 33 same-person pairs and catches 10 the name already
   catches; keep it as evidence); make a **generational suffix a hard veto,
   not a normalization step** (11 of 166 homonym pairs are father/son
   separated only by `JR`/`III`); and match a middle initial to a middle
   name (`mi`, not `full`). Adopt all three?
4. **DEF 14A eligibility.** 58.7% of its rows are not person names
   ([ticket 10](10-fix-proxy-executive-name-parser-leak.md)). Its own n is
   51 (LCB95 0.9496). Does the pooled figure carry proxy, or does proxy
   stay ineligible until the parser is fixed and re-measured on its own?

Whatever is decided replaces ticket 02 §4's Tier B row and feeds the
Person Q11 amendment already with Codex.
