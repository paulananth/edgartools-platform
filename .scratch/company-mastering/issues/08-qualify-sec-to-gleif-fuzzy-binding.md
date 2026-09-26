# Qualify the first SEC-to-GLEIF Company binding rule

Type: task
Status: done (2026-09-26 ET): every item done except the wrong-link reversal, moved to ticket 13. The two rules are declared, not active; switching them on is a separate approval after ticket 13.
Blocked by: none (ticket 04's identifier rules are built; the rules here are declared, not active)

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
- [x] Production: the Name Census builder and its pin in the SEC bundle; SEC
  adapter v5 (business address, census entry) and GLEIF adapter v2
  (headquarters postcode and country) into `provenance.matching`.
- [x] Production: the `name_binding` family (rule check, 95% bar, measured
  activation), its primitives, `clean/matching.py` proposing in the Merge
  Stage in both directions (a GLEIF record meeting a bound SEC record, and an
  SEC record meeting a waiting GLEIF record), the two rules in
  `company.json` declared and inactive, their PROOFs pinned with a CI
  re-score.
- [ ] A wrong link is reversible by evidence-bound reversal, and a Match
  Exclusion stops it recurring: tests. **Moved out of this ticket, not done
  here** (to [ticket 13](13-correct-an-incorrect-company-link.md)): the
  Stage has no identity correction yet (see "Decisions made while building").
  It is a new ticket and blocks switching either rule on.
- [x] Apple, Microsoft, Shell and ASML each end as one master with CIK and
  LEI on real PostgreSQL 16. Shell does since ticket 14 landed SEC's
  `countryCode` (PR #720, merged `843228bd`, 2026-09-26 07:57 ET).
- [x] Unit, architecture and PG16 suites (1,666 and 148 passed at
  `fa916ddb`); three-axis `/code-review` on the approval commit (no blocking
  finding; GoF: leave it).
- [x] CI green on PR #713's final head, then merge on the operator's word
  (merged `b4faa6ac`, 2026-09-25).
- [x] Plain-English brief; operator approved the matching rules' fingerprint
  `983352e81d295a165a1391e82fa8a24a710e6f638361a577f18f541917fd4049` and
  asked for the merge (2026-09-25 15:21 ET). It approves the two rules as
  **declared, not active**: they moved into `policies/company.json`, which is
  now the live policy at that fingerprint; `automatic_rules` still names only
  the Account hold-back. The proofs keep no approval: switching a rule on is
  a separate decision, after the identity-correction ticket.

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

## Progress note (Claude, 2026-09-25 evening) — resume here

Branch `claude/company-mastering-08-sec-gleif-matching`, worktree
`edgartools-platform-worktrees/claude-cm-08`. Done and pushed: research, both
rules measured and passing (`research/08-1-*`, `08-2-*`), `clean/names.py`,
`clean/name_census.py`, `mdm name-census`, SEC adapter v5 and GLEIF
`provenance.matching`.

Known production gap: silver `sec_company_address` keeps `stateOrCountry`
only, not SEC's `countryCode`, so 10 postcode matches that rely on
`countryCode` (Shell among them) wait in production. Fix is a separate warehouse
change (add `country_code` to silver); raise it in the operator brief.

Next, in order:
1. `primitives.py`: register `name_census_match@1`, `gleif_entity_eligible@1`,
   `holds_no_other_lei@1`, `jurisdiction_agrees@1`,
   `jurisdictions_do_not_conflict@1`, `postal_agrees@1` (family
   `name_binding`, `_runs_in_the_merge_stage`).
2. `activation.py`: `RULE_CHECKS["name_binding"]` (emits bind, on_no_match
   wait only, holder_source set, must call `name_census_match@1` and one of
   jurisdiction/postal); `ACTIVATIONS["measured"]` accepts `name_binding`;
   `_check_measured` allows verdict `bind` for that family (it checks
   `verdict in KINDS` today); `ACCEPTED_BARS[("company","name_binding")]`
   0.95/0.95; `company.json` `bars.name_binding`.
3. `clean/matching.py` `propose()`, same shape as `binding.nothing()`; both
   directions (GLEIF record meets a bound SEC record; SEC record meets a
   waiting GLEIF record); the census entry must name exactly this CIK and this
   LEI with the GLEIF record's `gleif_last_update`; re-derive both keys; veto
   a Company already holding another LEI. `MergeStage.propose` combines it
   with `binding.propose`, identifier proposals first.
4. The two rules into `company.json` (declared, inactive) from
   `research/08-rules.json` (jurisdiction .1, postal .2); PROOFs + pending
   activations; update the digest pins (the active fingerprint `35250dad…`
   changes); CI re-score test over `08-1`/`08-2` files.
5. PG16: a matching integration test; four-company test uses the rule instead
   of the operator-picked PAIRS (Shell waits unless countryCode lands).
6. Parity: production census and rule over one whole capture vs research
   coverage `97e5d118…` (expect 3,040 plus explained differences).
7. Unit/architecture/PG16 suites, three-axis review, CI, plain-English brief.

## Decisions made while building (Claude, 2026-09-25 evening)

Recorded from the three-axis review (Standards, Spec, GoF).

- **Census freshness is checked per record, not per publication.** A GLEIF
  record in the Stage carries no archive hash, by design: delivery details
  are not source assertions. So the rule requires the census's recorded
  `LastUpdateDate` for the LEI to equal the Stage record's
  `gleif_last_update`. A record GLEIF changed since the census waits. A new
  GLEIF entity that took the same name after the census is **not** caught;
  the census must be rebuilt for each full Golden Copy (`local-operations.md`).
- **The rules are proposed beside the live policy, not in it.**
  `policies/proposals/company-name-matching.json` is not read by
  `load_kinds`, so the live fingerprint stays `35250dad…`, the operator's
  approval of ticket 12. The operator approves the fingerprint of
  `name_matching_policy()`: `983352e8…` with the rules declared. On approval,
  the rules move into `company.json`. (Done 2026-09-25 15:21 ET: the
  proposal file and `load_proposal` are gone; the live policy is `983352e8…`.)
- **A rule's arguments decide.** Every name-binding test reads its declared
  fields, paths, normalizers and code table, and refuses one it cannot honour.
  A unit test holds the registry equal to what `matching.py` implements.
- **Blocking activation, not this PR: undoing a wrong link.** The Stage cannot
  yet move or undo an established source binding ("requires a correction
  contract"), and a Match Exclusion is between two Companies, not between a
  record and a Company. Undoing a wrong link and blocking it from recurring
  needs an identity-correction capability; it is a new ticket and must land
  before either rule is switched on.
- **Blocking automatic Companies: the identifier rules.** The live policy
  activates no ticket 04 identifier rule yet, so no SEC record holds a
  Company automatically. The four-company test activates them as fixtures.
- **Parity (2026-09-25, `research/08-parity.json`).** The production census
  (`107c0e04…`, 76,117 entries) and rule tests over all 76,230 SEC filers
  and the full Golden Copy bind the same 3,050 Companies as the research
  (0 differences). Read as silver lands the SEC address, 3,040 bind: the 10
  missing are exactly the `countryCode`-only filers, Shell among them.
