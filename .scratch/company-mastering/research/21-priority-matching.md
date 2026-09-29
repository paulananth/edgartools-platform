# Research 21: priority (cascade) matching, SEC to GLEIF

On 2026-09-27 the operator asked for this. SEC-to-GLEIF matching should
become **priority matching**:
- first match on every field (legal name plus full address);
- merge what matches;
- then drop fields one at a time (street, then city, ...) to merge more;
- each later pass takes only the records still unmatched.

This note covers four things:
- what the primary sources say about doing that correctly;
- how company addresses should be compared;
- which SEC and GLEIF address pairings are sound;
- a concrete pass ladder, with its safeguards and proof.

Measured 2026-09-27 (evening, ET). There were zero SEC and GLEIF requests.
sec.gov was not read. SEC fields are cited from this repo only.

## The answer first

1. **Cascades are a standard, documented method.** The Census Bureau's PVS
   and ONS both use one. The rules are clear:
   - strictest pass first;
   - a record matched in one pass does not go on to the next;
   - each pass's links are reviewed separately.

   But ONS chose *not* to cascade in its most demanding linkage. It ran every
   record through every key and sent conflicts to clerical review (§1).
2. **The engine already cascades.** Identifier rules run first, then the name
   rules. "A name match never re-binds" (`matching.py`, `propose`). The rules
   in research 08 are already a two-rung ladder: jurisdiction, then postal
   code. What is new here is a rung that uses **street address to relax
   name uniqueness**, not to relax the address.
3. **Registered-agent addresses must never count as evidence, whether legal
   or HQ.**
   - The two most shared addresses in GLEIF are 251 Little Falls Dr (46,408
     LEIs) and 1209 Orange St (43,650 LEIs).
   - 6,934 LEIs give 1209 Orange St as their **headquarters** address.

   So "compare only HQ" is not enough (§2).
4. **Address alone cannot tell a parent from its subsidiary.** They share the
   HQ. For example, 4,062 LEIs sit at 200 West St, New York. So kept legal
   form and the jurisdiction-conflict veto must stay in **every** pass (§4).
5. **Business address against GLEIF HQ is the sound pairing.** It gives
   nearly every agreement in the measurement. The SEC mailing address adds
   almost nothing and brings PO boxes with it (§3, §4).
6. **Recommended ladder, top to bottom:**
   - the existing jurisdiction rung;
   - the existing postal rung;
   - **one new rung**: name plus full business-to-HQ street address, unique
     among *all* GLEIF holders of the name.

   Stop there. City-only, country-only and name-alone passes are not sound
   (§5).

   **On today's population, rung 3 cannot activate.** The Companies it would
   newly bind number **39, 47 or 48** of 6,414, depending on the
   generic-address cut-off. That is with every one of its conditions
   applied (§4). So for now the ladder is the two existing rungs.
7. **Each rung needs its own proof.** Take a labelled sample of its
   *marginal* links, in engine order, and require a one-sided Wilson lower
   bound of at least 95%. With zero errors that needs at least 52 links.
   Rung 3's 39 to 48 fall short even if every link were correct. It must
   wait for a larger population, such as the full SEC Company kind (§5).

## Inputs (pinned)

| Input | sha256 | What |
|---|---|---|
| `cm08-coverage-2.jsonl` | `97e5d118…6509` | 6,414 Account hold-back Companies, their name-rule outcome, and their SEC business and mailing addresses (as pinned by `08-parity.json`; research 19) |
| `cm08-sec-scan.jsonl` | `bdf379bf…c0d1` | all 76,230 SEC filers: names, former names, addresses (ticket 08 bronze scan) |
| `cm08-gleif-all.jsonl` | `e4e6fe8a…1d9f` | all 3,428,477 GLEIF Level 1 records, 2026-09-11 16:00 UTC Golden Copy, legal and HQ address |

The measurement scripts and outputs are kept outside the repo, in the session
scratchpad `r21/`:
- `measure.py` (`a54edfe6…`) wrote `measure.json` (`17c4fa00…`);
- `measure2.py` (`579ea50f…`) wrote `measure2.json` (`8e809e9e…`);
- `measure3.py` (`28ab6462…`) wrote `measure3.json` (`79bd6be4…`).

They use the production name keys (`names.legal_form_key`,
`names.sec_legal_form_key`) and the production EDGAR code table
(`names.edgar_jurisdiction`).

These are coverage counts, not a proof. Nothing here was labelled.

## 1. What the primary sources say about multi-pass matching

### How a cascade works

- **Census Bureau PVS.** Wagner and Layne (2014), *The Person
  Identification Validation System (PVS)*, CARRA Working Paper 2014-01,
  <https://www.census.gov/content/dam/Census/library/working-papers/2014/adrm/carra-wp-2014-01.pdf>:
  - "In general, each successive pass is less restrictive than the previous
    one." (§3.3.3)
  - "the blocking key for the first pass is highly restrictive and has a low
    probability of reporting error. (An example is an exact address match.)"
    (§3.3.4)
  - Across modules: "Incoming records cascade through the PVS – and only
    records failing a particular matching module proceed on to the next
    module." (§3.4)
  - PVS's own address matching is itself a ladder: first "the full address,
    including the within structure unit number", then "basic street address
    (BSA) without the within-structure unit number" (§3.3.2).
- **ONS hierarchical matchkeys.** Wray, McLaughlin, Vellanki, White,
  Plachta and Maizey (2024), "Evaluation of an Optimal Method for Ordering
  Hierarchical Matchkeys in Data Linkage at the Office for National
  Statistics", *IJPDS* 9(5), <https://doi.org/10.23889/ijpds.v9i5.2656>:
  - hierarchical matchkeys apply "a list of conditions to classify links,
    where records can only be linked once";
  - "The aim of the hierarchy is to classify correct links by running higher
    precision matchkeys first, removing linked records from the matching
    pool, and then running lower quality keys so that they are less likely
    to make incorrect links."
  - The paper exists because the **order** changes the result. Its authors
    graded orderings against gold-standard links for precision and recall.
- **Splink** runs rules-based (deterministic) linkage: "While Splink is
  primarily a tool for probabilistic records linkage, it includes
  functionality to perform deterministic (i.e. rules based) linkage." Each
  rule is a `block_on(...)` set of exact-equal fields. A pair matching any
  rule is a match with "a match probability of 1".
  - Source: <https://moj-analytical-services.github.io/splink/demos/examples/duckdb/deterministic_dedupe.html>.
  - Splink produces "all record comparisons that satisfy at least one of
    your blocking rules". Its docs do not describe a pass order
    (<https://moj-analytical-services.github.io/splink/topic_guides/blocking/blocking_rules.html>).
  - So Splink's deterministic mode is an OR of rules, not a cascade. The
    ordering and one-to-one logic would be ours to write.

### Where cascades go wrong: the counter-example

ONS, *Linkage methods for Census 2021 in England and Wales* (15 December
2022),
<https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates/methodologies/linkagemethodsforcensus2021inenglandandwales>,
section "Deterministic matching":
- "Deterministic algorithms often use hierarchical matchkeys, which means
  that the matchkeys are ordered by strictness, and once a census or CCS
  record is matched it will not then be considered for matching in the
  remaining matchkeys. Because of the high precision and recall targets for
  this linkage, hierarchical matching was not used, and all records were
  passed through all matchkeys. This ensured matches were not missed just
  because they were made on a weaker matchkey. It also meant there was the
  possibility of making conflicting or non-unique matches within or across
  matchkeys".
- A record matched by two keys to two different records is sent to
  "Clerical resolution". Only a unique match is accepted automatically.

The lesson for us: a cascade hides conflicts. Suppose an early pass binds
GLEIF entity X to filer A. Filer B may be a better match for X, but a later
pass never sees X, so nobody learns of the conflict. The engine already
guards the GLEIF side ("a name match never re-binds"). The other safeguard
is to count **uniqueness over the whole source**, not over what is left
(§5).

### One-to-one

- **PVS is one-to-many by design.** "All Numident records are always
  available for linking in every pass", and only "the records from the
  incoming file for these linked cases are excluded from all remaining
  passes" (§3.3.3). After each module, a post-processing step checks for
  "more than one SSN assigned to a source record. If so, the best link is
  selected. If no best SSN is determined, all SSNs assigned are dropped"
  (§3.4.2).
- **ONS (Wray 2024): "records can only be linked once".** That is,
  one-to-one.
- **NCHS keeps one pair per patient.** It "selects only one pair per patient
  on the NHCS file". Source: National Center for Health Statistics, *The
  Linkage of the 2016 National Hospital Care Survey to the 2016/2017
  National Death Index: Methodology Overview and Analytic Considerations*
  (document version 2022-01-26), Appendix §3,
  <https://www.cdc.gov/nchs/data/datalinkage/NHCS16-NDI16-17-Methodology-Analytic-Consider.pdf>.

**MDM needs both sides removed, not the PVS pattern.** A GLEIF record binds
once, and a Company holds one LEI (`holds_no_other_lei@1` in `matching.py`).
PVS's always-available reference file would let one LEI join two Companies
in two passes.

### Measuring each pass, and where relaxation stops

- **PVS reviews each pass separately.** Its analysis program lists "links,
  by pass number, with the score". An analyst "can review matches in the
  third (less restrictive) pass with the lowest score to determine if the
  parameter estimates are yielding sensible links" (§3.3.4).
- **ONS stopped relaxing when false positives rose.** "Three of the 35
  person matchkeys were not used to automatically match records, as their
  false positive rates were deemed too high. Instead of removing these
  matchkeys ... all matches made by these matchkeys were clerically
  reviewed". Its quality checks sampled for false positives and for false
  negatives (ONS 2022, "Results and quality assurance").
- **NCHS's deterministic step validates its key against other fields.** It
  retains an SSN match only "If the ratio of matching identifiers to
  non-missing identifiers is greater than 50%". Its probabilistic threshold
  "was set at the level that produced the lowest estimated total error"
  (NCHS 2022, Appendix §1 and §3).

So each pass has its own measured precision. A pass that cannot reach the
bar is not tuned into passing. Its links go to review instead.

### The probabilistic alternative

Fellegi and Sunter (1969), "A Theory for Record Linkage", *JASA* 64(328):
1183–1210, <https://doi.org/10.1080/01621459.1969.10501049>, is the
foundation that NCHS and Splink cite.
- Every field comparison gets an *m* probability, "the probability of a
  given observation given the records are a match".
- It also gets a *u* probability, "a measure of coincidence/cardinality".
- Source for both definitions:
  <https://moj-analytical-services.github.io/splink/topic_guides/theory/fellegi_sunter.html>.

Term-frequency adjustment makes a shared *common* value weaker evidence than
a shared rare one. Splink's example is surname "Smith"
(<https://moj-analytical-services.github.io/splink/topic_guides/comparisons/term-frequency.html>).
A deterministic ladder has no weights, so a frequency cut-off for "generic"
addresses (§2) stands in for the *u* side.

**Senzing** encodes the same idea as principles. Source: *Principle-Based
Entity Resolution Explained*,
<https://senzing.com/wp-content/uploads/Principle-Based-Entity-Resolution-092519.pdf>.
- An address is frequency "Few (FF) – only a few entities should have this
  value".
- When a value is over-shared, "our software detects it, labels that SSN as
  generic and reevaluates all prior records with that number".
- Its default rule `MULT_FF+CLOSE_NAME` matches two records "sharing
  multiple FFs and a close NAME ... unless they have conflicting exclusive
  attributes".

That last rule is the same shape as ours: address plus name, vetoed by a
conflicting exclusive attribute. For us that attribute is jurisdiction of
incorporation.

## 2. Comparing company addresses

### Standardization

- **USPS Publication 28** defines the target: "A standardized address is one
  that includes all required address elements and that uses the Postal
  Service standard abbreviations" (§211,
  <https://pe.usps.com/text/pub28/28c1_004.htm>).
  - Appendix C1 lists the street-suffix abbreviations (STREET → ST, AVENUE →
    AVE, BOULEVARD → BLVD; <https://pe.usps.com/text/pub28/28apc_002.htm>).
  - §213 lists the unit designators: "APARTMENT APT BUILDING BLDG FLOOR FL
    SUITE STE UNIT UNIT ROOM RM DEPARTMENT DEPT"
    (<https://pe.usps.com/text/pub28/28c2_003.htm>).
- **libpostal** is "A C library for parsing/normalizing street addresses
  around the world using statistical NLP and open data". Its
  `expand_address` does abbreviation expansion in many languages
  (<https://github.com/openvenues/libpostal>). It is a compiled dependency
  with a large model.
  - Given the lean-MDM preference, it is an option for non-US addresses
    later, not a recommendation now.

**Recommended key.** Build a small, versioned normalizer, as `names.py` does
for legal forms. It keeps:
- country;
- postal code (5 digits in the US, the whole code elsewhere);
- the house number;
- the street name, with Pub 28 C1 suffixes and directionals unified.

It stops at the first Pub 28 unit designator. The measurement here used
exactly that key (`measure_lib.py`).

### Suite numbers and ZIP+4

- **Drop the suite.** Pub 28 §213 puts the unit "at the end of the Delivery
  Address Line", but SEC often puts the suite in `street2`
  (`bronze_submission_extractors.py`, `stage_address_loader`). PVS likewise
  keeps a pass "without the within-structure unit number" (§3.3.2).
- **Compare 5 digits.** Of 6,011 business addresses with a ZIP among the
  6,414 Companies, only **247** carry ZIP+4. `names._postal` already cuts a
  US ZIP to five digits.

### Registered-agent and other shared addresses

Count distinct LEIs per address key (country, postcode, number, street)
across all 3,428,477 GLEIF records:

| Address | LEIs (legal or HQ) | of which HQ |
|---|---:|---:|
| 251 Little Falls Dr, 19808 (CSC) | 46,408 | 6,235 |
| 1209 Orange St, 19801 (CT Corporation) | 43,650 | 6,934 |
| 850 New Burton Rd, 19904 | 8,744 | — |
| 2711 Centerville Rd, 19808 | 4,435 | 1,705 |
| 190 Elgin Ave, KY1-9008 (Cayman) | 4,104 | 1,683 |
| 200 West St, 10282 (Goldman Sachs HQ) | 4,062 | 4,051 |

More measured facts:
- **Agent text.**
  - Of 315,046 GENERAL entities with a US legal address, **118,153** have
    registered-agent text in their legal address.
  - **16,938** have it in their HQ address.
  - Across all GENERAL entities, 21,677 HQ addresses carry agent text.
- **Funds.** 8,149 FUND HQ addresses carry agent text.
- **Sharing is heavy.** 687,564 GLEIF address uses are at an address shared
  by 10 or more LEIs, and 194,262 at one shared by 1,000 or more.
- **Frequency also hits real headquarters.** 200 West St is a real HQ shared
  by thousands of affiliates. **1,002** of the 6,414 Companies have a
  business address that 10 or more GLEIF LEIs also use.
  - At such an address, agreement cannot tell the listed parent from its
    subsidiaries. Only the name, with its legal form kept, can.

GLEIF itself flags some of this. The optional `MailRouting` field
"MAY contain explicit routing information or 'care of' address". It
"SHALL be used" when a fund's or government entity's address "is one of a
different entity". Source: GLEIF, *State Transition and Validation Rules
for Common Data File formats* v2.8.5 (2025-07-03), §2.7, §3.13, §3.14,
<https://www.gleif.org/lei-data/access-and-use-lei-data/level-1-data-lei-cdf-3-1-format/2025-07-03_state-transition-validation-rules_2.8.5_final.pdf>.

The repo's GLEIF contract does not read `MailRouting` yet
(`rules/sources/gleif/source.yaml`). The "C/O ..." text often sits in
`FirstAddressLine` anyway. Two examples from the extract:
- Hutchin Hill Capital's legal address is "C/O CORPORATION SERVICE COMPANY,
  251 LITTLE FALLS DRIVE";
- a Fidelity fund's HQ is "C/O FIDELITY MANAGEMENT & RESEARCH COMPANY LLC,
  CORPORATION TRUST CENTER, 1209 ORANGE ST".

**So an address is excluded as evidence when any of these holds:**
- `MailRouting` is present, once the contract carries it;
- the agent pattern matches. The pattern already exists in
  `08-measure-1.py` and `08-dev-levers.py`, and it should become versioned
  reference data;
- the address key is shared by at least a set number of LEIs. This is
  Senzing's "generic".

The cut-off is a policy value. At 10 LEIs it removes 718 of today's 2,855
jurisdiction binds' HQ addresses from address evidence. At 100 it removes
far fewer (§4). Pick it with a labelled sample, not by eye.

## 3. Which SEC and GLEIF addresses to pair

**GLEIF**, per the LEI-CDF 3.1 documentation
(<https://www.gleif.org/content/4_lei-data/1_access-and-use-lei-data/2_level-1-data-lei-cdf-3-1-format/lei-cdf_version_3.1-documentation.html>)
and the State Transition rules v2.8.5:
- **LegalAddress** is "The address of the Legal Entity as recorded in the
  registration of the Legal Entity in its legal jurisdiction" (§3.13).
  - In the extract, **118,153 of 315,046** (38%) US GENERAL legal
    addresses carry registered-agent text (§2).
- **HeadquartersAddress** "SHALL be the address of the main office or center
  of control of a company or organization" (§3.14).
- "LegalAddress and HeadquartersAddress MAY be the same". If the registry
  holds only one address, they "SHALL be the same address", except for
  FUND and BRANCH (§2.7).
  - In the extract, 779,839 of 3,043,262 GENERAL records have equal legal
    and HQ keys.
- For a fund, the HQ "SHALL be the registered address of the fund managing
  entity" (§3.14). A fund's address therefore names its manager, not the
  fund. Funds are outside the Company kind anyway.

**SEC**, from this repo only:
- `submissions.json` carries `addresses.business` and `addresses.mailing`.
  Each has `street1`, `street2`, `city`, `stateOrCountry`, `zipCode` and
  `countryCode` (`edgar_warehouse/loaders/bronze_submission_extractors.py`,
  `stage_address_loader`).
- A foreign address carries its country in `countryCode` and leaves
  `stateOrCountry` empty (same file; `company_source._business_addresses`).
- The Company adapter pins only the **business** address
  (`company_source.py`, `_business_addresses`).

What the 6,414 Companies show:
- Business and mailing have the same key for **5,153**.
- The mailing address is a PO box for **298**. The business address is a PO
  box for 226.
- Registered-agent text appears in 24 business and 26 mailing addresses.

**Pairings, in order of soundness:**

| SEC | GLEIF | Verdict | Why |
|---|---|---|---|
| business | HQ | **use** | both mean the operating office. It gives nearly every agreement (§4) |
| business | legal | only as a fallback, never at an agent address | it added 33 unique agreements among today's 2,855 jurisdiction binds that business-to-HQ missed (893 vs 926); 38% of US legal addresses are an agent's |
| mailing | HQ or legal | **do not use** | the same as business in 80% of cases, so it adds almost nothing; otherwise often a PO box or an agent |

The measurement agrees. In every deferred bucket, business-to-HQ alone
found the unique candidate for all but at most two of the Companies that
"any of the four pairings" found (`measure.json`, `reach`).
- Among today's jurisdiction binds it was 893 of 926.
- The rest came from business-to-legal.

## 4. What each rung would reach (coverage, not proof)

A pass reaches a Company when exactly one GLEIF entity:
- holds the Company's name, with legal form kept (as its legal **or** other
  name, any category or status);
- agrees on the full business-to-HQ address (number, street and ZIP-5), or
  on business-to-legal as a fallback;
- is at a non-agent address below the generic cut-off.

The entity must also be GENERAL, ACTIVE and not DUPLICATE or ANNULLED
(`measure2.py`).

| Today's outcome (research 08) | Companies | Reached at cut-off 10 | at 100 | no cut-off |
|---|---:|---:|---:|---:|
| BIND jurisdiction | 2,855 | 907 | 1,104 | 1,160 |
| BIND postal | 195 | 109 | 124 | 129 |
| defer: name names several GLEIF entities | 103 | 29 | 32 | 33 |
| defer: another GLEIF entity has the name as another name | 55 | 9 | 13 | 13 |
| defer: name names several SEC filers | 27 | 4 | 7 | 9 |
| defer: no jurisdiction or postal agreement | 248 | 1 | 1 | 1 |
| defer: postal agrees, jurisdictions conflict | 70 | 34 | 43 | 44 |
| defer: INACTIVE / FUND / government | 12 | 0 | 0 | 0 |
| no GLEIF record with this name | 2,849 | 0 | 0 | 0 |

What the table says:
- **A strict "name + full address" top pass adds nothing new.** Every
  Company it reaches in the two BIND rows is already bound, to the same
  LEI.
- **The new yield is in three deferred buckets, all about name
  uniqueness.** There, the address picks one entity out of several holders
  of the name.
  - Examples: Wells Fargo & Company, Manitowoc, Trinity Industries, Target,
    Merck & Co. (`measure.json`, `examples`).
  - Research 19 found that an LEI rung reaches at most 8.

**Rung 3 with every condition applied** (`measure3.py`). The table above
counts address agreement only. Rung 3 (§5) also requires:
- no jurisdiction conflict, checked with the production
  `names.jurisdictions_conflict`;
- exactly one SEC filer carrying the name (current or former) at that
  business address.

| Deferred bucket | Rung 3 binds, cut-off 10 | at 100 | no cut-off |
|---|---:|---:|---:|
| name names several GLEIF entities | 26 | 28 | 29 |
| another GLEIF entity has the name as another name | 9 | 13 | 13 |
| name names several SEC filers | 3 | 5 | 5 |
| no jurisdiction or postal agreement | 1 | 1 | 1 |
| **Total new Companies** | **39** | **47** | **48** |

Compared with the first table, the veto holds back 2 to 3 more Companies,
the SEC-side test 2 to 5, and the legal-name and eligibility tests the
rest. **Every total is below the 52
correct links a 95% proof needs (§5).**

- **"No jurisdiction or postal agreement" (248) is untouched.** Those
  Companies already failed the postal code, so a finer address cannot
  agree.
- **"Postal agrees, jurisdictions conflict" (70) is the trap.** Full
  address agrees for 34 to 44 of them. This is exactly the AAON case that
  created the veto (`names.jurisdictions_conflict`): a parent and a
  same-named subsidiary at one HQ, incorporated in different states.
  Address agreement is not evidence against that. **Keep the veto.** If
  some of these are SEC state-code errors, a separate labelled rule must
  show it.
- **"No GLEIF record with this name" (2,849) cannot be reached** by any
  address pass while the SEC current name must equal a GLEIF **legal** name.
  That is today's key (research 08, step 1). A key that also accepts GLEIF
  other names does reach some of them; see the note below. Relaxing the *name* (transliterated
  names, a dropped legal-form suffix, research 19's Innate Pharma and Nexxen)
  is separate name-rule work.

**The field-dropping passes the operator described, measured the other way
round.** City-only and country-only agreement do not separate a parent from
a subsidiary. They also fall back on name uniqueness, which the census
already tests. A "name alone" pass is the census rule without its
place test. Research 08 measured what that costs: the dropped legal-form
misses (Wayfair Inc. vs WAYFAIR LLC) came from the name alone deciding.

**Note: a concurrent draft.** This directory also holds `21-tiers.py`
(sha256 `bd02d5d7…66f8`) and `21-tiers.json` (`48fa617d…bc76`). Another
session committed them on this branch in `3dad528e`. This research did not
write them.

Its docstring says:
- "No jurisdiction test";
- a pair is "one-to-one in that pass", with each pass taking "only the SEC
  filers and GLEIF entities still unmatched".

Its passes run down to "P6 name + country" and "P7 name alone". It matches
the SEC name against GLEIF legal **and other** names (`21-tiers.py`, line
149). That is why it reaches 80 Companies from the "no GLEIF record with
this name" bucket.

It binds 456 deferred Companies. Rung 3 under this note's safeguards binds
39 to 48. The difference is roughly what these choices buy:
- dropping the jurisdiction veto;
- counting uniqueness over what is left;
- accepting country-only and name-alone agreement.

§1 and §5 argue against all three.

## 5. Recommendation (for the operator; not a decision)

### The ladder

The engine keeps its order: identifier rules, then these rungs. Each rung
takes only GLEIF records not yet bound (`matching.propose`).

| Rung | Name test | Place test | Status |
|---|---|---|---|
| 1 | legal form kept; census-unique over **all** SEC and GLEIF name holders | SEC state of incorporation agrees with GLEIF jurisdiction | exists (research 08) |
| 2 | same as rung 1 | business ZIP agrees with GLEIF HQ postcode, same country; no jurisdiction conflict | exists (research 08) |
| 3 (new) | legal form kept; **not** census-unique. Among **all** GLEIF holders of the name (legal or other name, any category or status, branches aside), exactly one agrees on the address. That one is GENERAL, ACTIVE, not DUPLICATE or ANNULLED, and holds the name as its **legal** name. Exactly one SEC filer carrying the name (current or former) is at that business address | SEC business address = GLEIF HQ address (else, as a fallback, GLEIF legal address) on country, ZIP-5 (or foreign postcode), house number and Pub 28 street; neither side generic or agent; **no jurisdiction conflict** | new; needs proof |
| — | stop | city-only, country-only and name-alone passes are not built | — |

Rung 3 needs one more matching value in the Stage. Today the GLEIF contract
carries only the HQ postcode and country
(`rules/sources/gleif/source.yaml`, `matching`), so the full HQ street
would be a new contract version. It also needs an **address census** pinned
beside the Name Census: distinct LEIs and SEC filers per address key,
counted over the whole sources, because a Stage cannot count them.

### Safeguards, in every rung

1. **Uniqueness is counted over the whole source, never over what is left.**
   Suppose a name looks unique only because an earlier pass bound its
   sibling. Then one early error spreads down the ladder. That is the
   conflict ONS avoided by not cascading (§1).
2. **One-to-one on both sides.** A GLEIF record binds once ("a name match
   never re-binds"), and a Company holds one LEI (`holds_no_other_lei@1`).
   Two candidates means review (`ambiguous_name_match`), never "best
   score". This follows Wray (2024) and ONS's clerical resolution, not
   PVS's one-to-many reference file.
3. **Kept legal form and the jurisdiction-conflict veto** apply in every
   rung. This is Senzing's "unless they have conflicting exclusive
   attributes".
4. **Generic and agent addresses carry no evidence** (§2): `MailRouting`,
   the agent pattern, or the frequency cut-off.
5. **Eligibility is unchanged:** GENERAL, ACTIVE, not DUPLICATE or ANNULLED.
6. **A Company under review gains nothing** (`suspended_identifier`).

### Proving each rung

- **Measure the marginal links.** Each rung's sample is drawn from the
  links **that rung adds**, running the rungs in engine order. A rung's
  precision depends on what the rungs above it have already taken (Wray
  2024). Reordering or changing a rung means measuring again.
- **Same bar as today.** A rung activates only at a one-sided 95% Wilson
  lower bound (Wilson 1927, "Probable Inference, the Law of Succession,
  and Statistical Inference", *JASA* 22(158): 209–212,
  <https://doi.org/10.1080/01621459.1927.10502953>). This is
  `activation.wilson_lower_bound`.
  - With every link correct, the bound is n / (n + 2.706). So **at least 52
    correct links** are needed (research 19, §3).
- **Rung 3 cannot pass today.** With every condition applied, it newly
  binds 39, 47 or 48 Companies on 6,414, depending on the cut-off (§4).
  That is short of 52 even if every link were correct.
  - It waits for a larger population, such as the full SEC Company kind
    rather than the Account hold-back. Re-measure it then.
  - A rung that cannot reach 52 marginal links cannot activate alone. That
    is the hard stop on relaxing.
  - Until then, its would-be links can go to review as candidates. This
    needs no proof, because it binds nothing.
- **Add an adversarial arm,** as tickets 08 and 12 did. Include the
  jurisdiction-conflict pairs and pairs at shared corporate HQs (for
  example, 200 West St). Labellers then see the parent/subsidiary cases the
  rung is most likely to get wrong. Follow the existing labelling standard
  (`08-labelling-standard.md`).
- **The residue goes to review, not to a looser rung.** This is what ONS did
  with its three high-false-positive keys (§1). Rung 3's non-unique cases,
  and any vetoed pair whose address fully agrees, become review items.
  Nothing binds them automatically.

## Sources

Primary methods:
- Wagner, D. and Layne, M. (2014). *The Person Identification Validation
  System (PVS)*. U.S. Census Bureau, CARRA WP 2014-01.
  <https://www.census.gov/content/dam/Census/library/working-papers/2014/adrm/carra-wp-2014-01.pdf>
- ONS (2022-12-15). *Linkage methods for Census 2021 in England and Wales*.
  <https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates/methodologies/linkagemethodsforcensus2021inenglandandwales>
- Wray, M. et al. (2024). *IJPDS* 9(5). <https://doi.org/10.23889/ijpds.v9i5.2656>
- NCHS (2022). *The Linkage of the 2016 NHCS to the 2016/2017 NDI*.
  <https://www.cdc.gov/nchs/data/datalinkage/NHCS16-NDI16-17-Methodology-Analytic-Consider.pdf>
- Fellegi, I. and Sunter, A. (1969). *JASA* 64(328). <https://doi.org/10.1080/01621459.1969.10501049>
- Wilson, E. B. (1927). *JASA* 22(158). <https://doi.org/10.1080/01621459.1927.10502953>
- Splink documentation (deterministic linkage, blocking rules,
  Fellegi-Sunter, term frequency), links inline above.
- Senzing. *Principle-Based Entity Resolution Explained*.
  <https://senzing.com/wp-content/uploads/Principle-Based-Entity-Resolution-092519.pdf>

Addresses:
- USPS Publication 28, §211, §213, Appendix C1. <https://pe.usps.com/text/pub28/welcome.htm>
- libpostal. <https://github.com/openvenues/libpostal>

GLEIF:
- LEI-CDF 3.1 documentation (link above).
- State Transition and Validation Rules v2.8.5 (2025-07-03), §2.7, §3.13,
  §3.14 (link above).

Repo:
- `edgar_warehouse/mdm/clean/matching.py`, `names.py`, `name_census.py`,
  `activation.py`, `company_source.py`
- `edgar_warehouse/loaders/bronze_submission_extractors.py`
- `rules/sources/gleif/source.yaml`
- research `08-draft-rule.md`, `19-lei-matching-at-lower-priority.md`
