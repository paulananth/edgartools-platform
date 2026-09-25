# Qualify the first SEC-to-GLEIF Company binding rule

Type: task
Status: open
Blocked by: 04

## Question

Operator, 2026-09-24: one real Company has **one** master record, holding the
CIK from SEC and the LEI from GLEIF; both source records stay in the Stage.
Two master records for one Company is the failure to prevent, not a state to
consolidate later.

Tickets 03 and 04 make a record recognisable again **by the identifier its own
source carries**: an SEC record by CIK, a GLEIF record by an LEI already on
the Company.
Neither joins the two sources. The SEC adapter declares `cik` as its only
identifier (`company_source.py:50`), GLEIF Level 1 carries no CIK, and Q14
forbids treating an LEI as a CIK crosswalk merely because both values exist.

SEC submissions **do** carry an `lei` key, but the adapter does not map it and
it was null for all four Companies checked on 2026-09-23 (Apple, Microsoft,
Shell, ASML; bronze `submissions/sec/cik=*/main/`). Where SEC populates it, the
record states its own LEI, which is not the crosswalk Q14 forbids and could be
an identifier path for part of the universe. **First step of this ticket:
measure how often it is populated across bronze**, which sets how much of the
join fuzzy matching must carry. For every Company without it, the first link
between its SEC and GLEIF records can only come from the qualified fuzzy
matching Company Q4 accepted: name, jurisdiction and address evidence,
corroborated where identifiers allow.

**Matching fields named by the operator** (2026-09-24): company name, ticker
or CUSIP. What each side carries, checked on the four Companies' real records
(GLEIF golden copy 2026-09-11, SEC bronze submissions):

| Field | SEC | GLEIF Level 1 |
| --- | --- | --- |
| Company name | yes (`name`) | yes (`LegalName`, `OtherEntityNames`) |
| Ticker | yes (`tickers`) | **no** |
| CUSIP | not in submissions | **no** |
| Country / address | yes | yes (legal and headquarters) |

A CUSIP reaches GLEIF only through GLEIF's separate **ISIN-to-LEI mapping
file** (a US ISIN embeds the CUSIP). GLEIF ticket 11 routed that file to a later
Security consumer, and its coverage is partial (participating agencies and new
ISINs). So today a ticker or CUSIP cannot be compared with a GLEIF record
directly; name plus country and address can.

**Decided** (operator, 2026-09-24): the first matching rule compares **name,
country and address** only. GLEIF's ISIN-to-LEI file comes afterwards, as a
second, stronger check where it has coverage — a CUSIP match confirms a name
match rather than replacing it. It waits because it brings a new source into
scope and needs a CUSIP on the SEC side, which the SEC Company data lacks.

Without this ticket the Proving Run (05) reports every SEC Company as "no
GLEIF match", which Q2 counts as a *completed* outcome. The milestone would
look finished with zero SEC Companies linked to GLEIF, failing the completion
gate's order 4 ("Qualified automatic decisions tie SEC CIK and GLEIF LEI to one
immutable Company").

Build and qualify one fuzzy binding rule family for SEC → GLEIF Company:

- the candidate predicate and its named, versioned primitives, run inside the
  same Merge Stage transaction ticket 03 builds, never as a separate matcher;
- its statistical gate per the accepted policy — **95% precision** at a
  one-sided 95% lower bound (confidence bands, operator 2026-09-24; was
  99.9%), with 50-95% waiting in the Stage and below 50% going to a Steward, measured per rule family on a held-out set **independent** of
  the rule's authoring; the 308 adjudicated seed links are comparison only, not
  qualification truth;
- ambiguous candidates defer and contribute no GLEIF fields (Q2, Q6);
  a verified no-match is a completed outcome only after the rule has actually
  run;
- a wrong link is reversible through evidence-bound reversal, and a Match
  Exclusion stops it recurring.

Out of this ticket: consolidating two already-published Company IDs (Q10, Q11
keep their own gate) and GLEIF-only parent creation (Q7).

## Why it sits after 04

The fuzzy rule proposes a link to a Company that already exists by CIK. The
identifier path must be in place first, so the rule's candidates are the
established masters and not per-record fresh mints.

## What 05 and 06 inherit

The Proving Run reports this family's verdicts beside the identifier rules',
and the activation approval names its digest separately: approving the
identifier rules does not approve this one.

## Checklist (Claude, 2026-09-25 13:50 ET)

Worked through without stopping, per the checklist rule. Stop only for a
fingerprint approval, a "same legal entity" case no ruling covers, or merge.

- [x] Step 1: SEC's own LEI and GLEIF authority `RA000665` join almost no
  Companies (2026-09-24 22:24 ET, `research/08-sec-lei-and-gleif-sec-authority.md`).
- [x] Re-base step 1's counts on the Account hold-back's 6,414 Companies:
  SEC's own LEI 10, `RA000665` 10 (2026-09-25 14:20 ET, `research/08-draft-rule.md`).
- [x] What the Stage can compare, and how candidates are found: the design
  below (Name Census as pinned evidence; matching evidence in
  `provenance.matching`; SEC business address pinned like the tickers).
- [x] Development analysis (2026-09-25 14:20 ET, `research/08-draft-rule.md`):
  keeping the legal form in the name is the lever (0.941 to 0.976 on the
  development pairs); the SEC state-in-country and agent-address faults are
  fixed; uniqueness counts every name over the whole GLEIF publication and
  every SEC filer.
- [x] Written labelling standard (`research/08-labelling-standard.md`), frozen
  before any label.
- [x] `/gof-refactor-reviewer`: no refactor first; a `name_binding` family
  beside identifier binding, a sibling `matching.py`, the census pinned like
  the ticker catalog.
- [x] Name, jurisdiction and postal tests are production code
  (`clean/names.py`); coverage through them reproduces the research byte for
  byte.
- [x] **Name-and-state rule** (`sec-gleif-name-jurisdiction` 2026-09-25.1):
  300/300, lower bound 0.9911, 0 of 257 adversarial. Passes
  (2026-09-25, `research/08-1-summary.json`).
- [x] **Name-and-postcode rule** (`sec-gleif-name-postal` 2026-09-25.1):
  294/300 but 19 of 162 adversarial pairs wrong, every one a pair whose two
  sources name different places of incorporation (AAON, Inc.'s Oklahoma
  subsidiary). Fails.
- [x] **Postcode rule with state veto** (`sec-gleif-name-postal`
  2026-09-25.2) on a fresh draw that left out every earlier CIK: 300/300,
  0.9911, 0 of 315 adversarial. Passes (`research/08-2-summary.json`).
- [x] Coverage with both passing rules: 3,050 of 6,414 Companies bind
  (2,855 by state, 195 by postcode); Apple, Microsoft, Shell and ASML
  included.
- [ ] Production: the Name Census builder and its pin in the SEC bundle; SEC
  adapter v5 (business address, census entry) and GLEIF adapter v2
  (headquarters postcode and country) into `provenance.matching`.
- [ ] Production: the `name_binding` family (rule check, 95% bar, measured
  activation), its primitives, `clean/matching.py` proposing in the Merge
  Stage in both directions (a GLEIF record meeting a bound SEC record, and an
  SEC record meeting a waiting GLEIF record), the two rules in
  `company.json` declared and inactive, their PROOFs pinned with a CI
  re-score.
- [ ] A wrong link is reversible by evidence-bound reversal, and a Match
  Exclusion stops it recurring: tests.
- [ ] Apple, Microsoft, Shell and ASML each end as one master with CIK and
  LEI on real PostgreSQL 16.
- [ ] Unit, architecture and PG16 suites; three-axis `/code-review`; CI green.
- [ ] Plain-English brief; operator approves the matching rule's fingerprint;
  merge on the operator's word.

## Design (Claude, 2026-09-25 14:45 ET)

Technical choices made under the checklist rule; none needs a new operator
ruling. Evidence: `research/08-draft-rule.md`.

1. **Who binds to whom.** A GLEIF record waits in the Stage (operator,
   2026-09-24). The matching rule binds a waiting GLEIF record to the
   Company its SEC record already holds by CIK. It never creates a Company.
2. **The Name Census is pinned evidence, not a matcher.** A Stage holds a
   bounded scope, so it cannot count how many GLEIF entities or SEC filers
   carry a name. A census is built once, from the whole pinned GLEIF Level 1
   publication and the whole SEC capture (current and former names). For
   each SEC filer's name key it records which CIKs and which GLEIF legal
   entities carry that name. It is bound to its inputs: the GLEIF archive
   sha256, the SEC capture run and member hashes, and the name normalizer
   version. The SEC bundle pins its digest, as ticket 12 pinned the ticker
   catalog. The census only **proposes** a pair; the Merge Stage decides.
   It re-derives both name keys from the Stage rows and checks the
   jurisdiction or postal code itself. It defers when the census names
   another GLEIF publication, has no entry for the key, or names anything
   but exactly this CIK and this LEI.
3. **Matching evidence lives with the record, not in its fields.** The SEC
   business postal code and country, and the GLEIF headquarters postal code
   and country, go in each record's `provenance.matching`. So does the SEC
   record's census entry. Address as a Company field stays ticket 09's
   decision.
4. **Two rules, one per step.** A binding rule's tests all have to hold, and
   the policy language allows no "or". So the jurisdiction step and the
   postal step are two rules, each with its own proof and its own activation
   (`sec-gleif-name-jurisdiction`, `sec-gleif-name-postal`).
5. **Vetoes.**
   - The Company already holds a different LEI: a legal entity has one LEI.
   - The GLEIF entity is not GENERAL, not ACTIVE, or is DUPLICATE or
     ANNULLED.
6. **Activation.** It is statistical, at the operator's 95% bar for this
   family. It must not lower any other decision's bar: identifier binding
   stays deterministic, and merging two published Companies keeps its 99.9%.
