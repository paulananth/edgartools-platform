---
name: data-modeling
description: Decide where one profiled part of a data set sits in the model - its class, its master kind or code set, which identifiers decide identity and which are lookup only, how a code list becomes a code set (hierarchy, crosswalk, usage, hints), how a relationship is typed, and its time model - from approved profiling findings and the language the platform already has. Use when the operator asks what a part is in the model, which kind or code set a column belongs to, whether an identifier may join records, how a code list or relationship should be modeled, or to review the model itself.
---

# Data modeling

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

The boundary is [REQUIREMENTS.md](REQUIREMENTS.md). This skill decides
structure, with evidence and the existing language. It does not measure files
(data-profiling), write a contract (data-onboarding, refining-rules), write a
check (data-quality), or approve anything.

**Hand off when:**

- there are no approved findings (`approval.status: approved` in `findings.yaml`): data-profiling (`skills/data-profiling/SKILL.md`)
- the structure is accepted and the feed is new: data-onboarding (`skills/data-onboarding/SKILL.md`)
- a live feed's mapping or matching should change: refining-rules (`skills/refining-rules/SKILL.md`)
- a defect needs a check or a fix: data-quality (`skills/data-quality/SKILL.md`)

## Hard stops

| Never | Instead |
|---|---|
| Approve findings or a code set version, or write words the operator did not say | Ask one question, then wait |
| Guess a class, a key, a link or a meaning | Leave it unknown and name the failing tests from the findings |
| Add a kind, or treat a profile as a kind | A missing kind is an operator ruling |
| Join records on a lookup-only identifier, or merge on similar names | Records join only through a kind's Identifier Contract or a matching rule the operator switched on |
| Split one kind into loads by the identifier asked, or pair two identifiers of one master in a source's own rules | One record carries every identifier it has; the Merge Stage looks each one up in the Cross-reference and puts them on one master (operator, 2026-10-25) |
| Name a new relationship type when an existing one, or its inverse, means the same | Use it, or ask the operator why a second type is needed |
| Write rules, contracts, quality files, or a code set version | Hand off; drafts in RDM go through data-profiling's RDM steps |
| Request anything from a provider's live service | Use the captured files and this repo |
| Propose a domain rule (a key, an order of precedence, a definition) from the captured data alone | First find how a public standard or the main vendors do it. Write it in a research note the next decision reads, mark what is unverified, and follow the standard unless the operator rules otherwise |
| Write a table spec, or start a build, from its own ticket alone | Review every ticket it builds on and every build ticket that cites it: each ruling since it was written, each dependency it leaves out, each stale "or" a ruling closed, each hard case its test lacks. Record the findings on the spec's ticket and fix the stale tickets in the same change (operator, 2026-10-22: "Check the tickets related to financial review work") |

## What the platform already says

Read these before deciding, and use their words:

- `CONTEXT.md`: the glossary (data classes, code set, crosswalk, reference
  and master data hierarchies, the kinds and their profiles).
- `edgar_warehouse/mdm/clean/evidence.py`: `KINDS` (the master kinds) and
  `PROFILE_KINDS` (a profile and the kinds it may hang on).
- `rules/merge/kinds/<kind>.yaml`, `identifiers`: the kind's Identifier
  Contract, the namespaces that decide identity.
- RDM code set `mdm-relationship-types` (`rules/reference/published/`, pinned
  in `rules/merge/reference-pins.yaml`): every relationship type, a code whose
  properties are the kinds at its ends, profiles and whether it is a
  hierarchy, whose child codes are its capacities and whose definition is its
  meaning and source.
- `docs/specs/rdm/spec.md` and `docs/specs/agent-context/spec.md`: how
  reference data and agent context are kept.

Ask what is already held, only for the question at hand:

```bash
edgar-warehouse context <kind> --search "<words>"      # a master already held
edgar-warehouse context <code set> --search "<words>"  # a code already held
edgar-warehouse rdm list                                 # every code set
edgar-warehouse rdm describe <code set>                  # its meaning, version, where used, hints
edgar-warehouse mdm counts                               # how many entities exist
```

## Decision rules

### 1. Class

Take the class from the approved findings, and check it against the glossary:

| Class | The part... | Lives in |
|---|---|---|
| Master data | describes things with their own identity and lifecycle; grows with the business | MDM, as a kind |
| Reference data | gives other values their meaning; small, near-constant, changed as a whole new version | RDM, as a code set |
| Relationship | links two masters, with a type, ends, and dates | MDM, with its masters |
| Transaction data | records events or facts about masters over time; only grows | silver |
| Metadata | describes the data itself (counts, files, runs) | bookkeeping, not modeled here |

**One system of record: every master data field is on its master in MDM,
and only there** (operator, 2026-10-28: "all master data fields must be on
mdm"; operator, 2026-10-28: "silver must not have duplicate fields, it contredits the data governance principle one system of record"). A silver row holds the transaction's own facts and its links to
masters (the link's source key, then the master id); it never copies a master
field, not even the value that row filed. A field MDM lacks moves to MDM
first; then silver drops it.

A part that looks like two classes is usually two parts: a code list inside a
master file is reference data plus a master attribute that holds its codes.

### 2. A master part: its kind

- The kind is one of `KINDS`. A role a thing plays (an adviser, an auditor, a
  fund) is a profile on a kind (`PROFILE_KINDS`), never a kind.
- No kind fits: say why the part is master data, propose a name and a
  definition, and ask the operator. Stop.
- **One kind, however many identifiers.** Two identifier schemes for one
  thing (a national number and an international number) are two identifiers
  of one master, never two kinds, two contracts or two loads. A provider
  asked once per scheme still describes one thing: each answer is a record of
  the same kind that carries every identifier it has, and the Merge Stage
  puts them on one master. Pairing two schemes in a source's own rules, or
  loading one scheme after the other so the second can read the first, is the
  smell to remove.

### 3. Identity or cross-reference

The Cross-reference is the one table of every identifier a master carries,
each joined to the master id and marked matching or lookup only (operator,
2026-10-25: "cross_refrence table must hold all the identifiers", "no need
for identifier table"). For each identifier, decide which it is:

- **Matching:** a namespace the kind's Identifier Contract declares
  (`rules/merge/kinds/<kind>.yaml`, `identifiers`): two records with the same
  value are one entity. A record looks up each matching identifier first and
  mints a master only when none is found ("first lookup if not exists then
  master"). Records of two sources also join through the matching rules the
  operator switched on (`rules/merge/policy.yaml`, `automatic_rules`).
  Nothing else joins records.
- **Lookup only:** an identifier that one value can give to two different
  masters (a trading symbol, a vendor key). Measure it before you decide:
  count the values the data gives to two or more masters. It finds records
  and never joins them, even when two records share it.
- **Today:** the engine stores only lookup-only identifiers in the
  cross-reference (`cross_references`) and the matching ones apart
  (`identifiers`), one value per kind. The one table, with a list of values
  for one kind, is decided and not built; see the Examples.
- **Know the identifier's level.** Some identifiers name a thing at several
  levels (one trading line, one country group, the thing worldwide). Match on
  the level that every source's records carry and that pairs them; a level
  most records lack pairs nothing however unique it is. For each level,
  count the records that carry it and the pairs it makes, before choosing.
- **Read a clash before deciding.** For each value the data gives to two or
  more masters, compare those masters (name, type): the same means one thing
  under two identifiers (a renumbered one), different means the identifier is
  not unique at that level. Different on more than a handful: lookup only, or
  matching that sends a clash to review. Report both counts.
- **Who may join masters.** A source whose job is to answer by identifier
  (an identifier service) may show that two masters are one, by an
  identifier both share. A pair of identifiers a transaction source reports
  together never merges two masters: the record binds by its identifiers in a
  declared order (the strongest first), adds the others only when no master
  holds them, and never moves an identifier from one master to another.
- **The result must not depend on load order.** The same records give the
  same masters and the same identifiers on each, whichever source or bundle
  arrives first. Prove it by running every order (section 9).
- **No identifier at all:** an id made from the name (`name_id@1`) is the last
  resort, as a cross-reference too (data-profiling, "An id from a name").
- A new identity namespace changes how records merge: an operator ruling.

### 4. A reference part: its code set

- **One code set per list of codes with one meaning.** Codes of two meanings
  in one column (places and their types) are two code sets.
- **Check what exists first** (`rdm list`, `context <code set> --search`). A
  list that is already held gets a new version, never a second code set.
- **Each field of a code goes to exactly one place:**

  | The field is... | It becomes |
  |---|---|
  | what the code stands for, in a few words | the `label` |
  | what it stands for, in full | the `definition` |
  | another name for the same code | a `synonym` |
  | the code above it, itself a code of the same set | its `parent_code` (a reference hierarchy, with level names) |
  | a code of another list (a grouping, a standard's code) | a crosswalk row to that code set: `exact`, `close`, `broad` (the target is broader) or `narrow` |
  | a code of an outside standard RDM does not hold | a crosswalk row with `to_version: outside` |

- **Never make a grouping into parent codes when the grouping's values are not
  codes of this set:** the grouping values would become valid codes, and a
  check would accept them. Make the grouping its own small code set and link
  each code to it with a `broad` crosswalk row.
- **Write the semantic layer for agents:** `usage` (each store, object and
  field whose values are codes of this set, and how a value compares: `exact`
  or `upper_trimmed`) and `hints` (`meaning`, `use_when`, `avoid_when`,
  `example_question`), from evidence only.
- A field with no place stops the import: nothing is dropped silently.

### 5. A relationship: its type

- **Name it as reality does:** the term the source or the standard uses,
  never an invented one; variation (stated or calculated, an event type, a
  threshold) goes on the link, not into a new name. A rename is the
  operator's, one name at a time.
- **Look for an existing type first,** in both directions: a type whose ends
  are swapped and whose meaning is the same is its inverse. Two types for one
  fact (one per source, or one per direction) make every reader ask both; name
  the existing one, or ask the operator why a second is needed.
- **Check the ends:** the kinds at each end must be the type's `from` and `to`;
  a profile at an end is `from_profile` or `to_profile`.
- **Capacity, not type:** the role a person holds in a link (director,
  officer, owner) is a capacity of one type, not a new type. Check the type's
  name still describes every capacity it holds.
- **A hierarchy** (parent chains): say whether cycles are invalid or reviewed,
  whether one parent at a time holds per scope, and whether an ultimate parent
  is derived.
- **Dates:** each period has `valid_from` and `valid_to`; say what each comes
  from (stated, first seen, last seen). Prefer a date the source states for
  each record over the delivery's date, which is only a fallback. If a link's start must never move later, whatever a
  later delivery states, declare the type with `keeps_start`: an earlier
  start, even one backfilled, still moves it back.
- **Events that end links:** if the data holds a succession (one entity
  ceased and another took it over), declare it as a type with
  `ends_parent_links`, so the ceased entity's parent links end on its date.
- **Onboarded together or separately:** the findings' `onboard` says which.

### 6. A transaction part: its silver table

From the findings' silver spec: the grain (one row per what), the key, the
links to masters (the source key and the MDM id, with the overlap measured),
the time columns, and the load mode. The spec is advice; this skill does not
build the table.

- **A transaction row links to its master by the master id only.** The
  identifiers it reported are found through the Cross-reference; the one
  source key a link reads stays, since the writer fills the master id from it
  once that record is mastered.
- **A fact every row repeats about the master** (a category, a country, a
  currency the instrument is in) is a master field, so it must reach MDM: the
  value most rows report, none on a tie, on the kind's fields and the Dataset
  Contract, and not on the silver row (one system of record). Ask
  before taking a fact that describes the holder's view (a valuation level, a
  position) to the master: that one stays on the row.

### 7. Time

Keep two times apart: **business time** (`--as-of`: when it was true) and
**recorded time** (`--as-at`: when the platform knew it). For every part, say
which columns carry each (the findings' `time.as_of` and `time.as_at`), and
for a transaction part also its `event_time` (when the event happened) and,
for a time series, its `series` (key, time column, step). Each code set
version has its own `valid_from`; publishing the next one closes its
`valid_to` at the new one's `valid_from`. A code's own dates are business
time.

### 8. A child part: its key

A part that a master has many of (its listings, its offices, its lines)
is a child table on the master id, with a key of its own.

- **Ask what the provider's unit is.** It can be finer than the business
  unit: a thing listed once per venue can still come as one record per
  trading line (a line per currency). Count the business key's repeats in
  the data before proposing it; if it repeats, find what tells the repeats
  apart.
- **A column read from another column is a guess, not a key.** A value
  taken from a code's suffix, or a default where the source states none, is
  a column and an index; prove it unique before it is any part of a key.
- **Prefer the provider's own identifier of its unit** when it has one and
  the data shows it unique: nothing is dropped, and the business key becomes
  an index.
- **Say what one row is, in one sentence,** and give the count of rows the
  key would drop or merge (zero, or the operator decides).

### 9. Prove the model on the data before building

A decision read from code or a glossary is not proof: the untested case is
where a gap hides. Before a build starts:

1. **Pick the archetypes by shape, at run time:** the common case; a
   look-alike that must stay apart (two things sharing a name or an issuer);
   a case that carries only the weaker identifier; the case with the most
   rows (the most lines, the most reports).
2. **Run the decided rules in memory** over the captured files for those
   cases: a short program outside the repository, reading the captures,
   printing counts and shapes only. Run every load order.
3. **Report per case:** masters formed, the identifier kinds each holds and
   their counts, what each source's records did (bind, mint, merge), and
   whether every order gave the same result.
4. **Then measure the whole population** for each rule the cases exercised:
   the records it would merge, drop, set aside or leave with one identifier.
   A count above a handful is the operator's question, with the count and a
   recommendation, before the build.

## Workflow

1. **Name the part.** If the operator has not said which part, ask and stop.
2. **Read the approved findings** for it: `class`, `record_key`,
   `identifiers`, `relationships`, `hierarchies`, `silver`. Missing or not
   approved: hand off to data-profiling.
3. **Read what the platform already says** (above) and ask what is held.
4. **Decide with the rules above,** one part at a time. Mark every unknown,
   with the failing test that left it unknown. Measure every proposed key and
   every identifier's uniqueness on the data before proposing it; a key or a
   matching identifier goes to the operator with its repeat count.
5. **Write the decision in plain words:** class; kind, code set or silver
   table; identity and cross-references; for a code set, where each field
   goes, its usage and hints; for a relationship, the type, its ends, its
   capacity and its dates; the time columns.
6. **Ask at most one question** when the choice is the operator's: a new kind,
   a new identity namespace, a second type for one fact, or which of two
   fields is the identity. Give the recommendation. Only the part it decides
   waits; carry on with the parts it does not touch.
7. **Prove the model on the data** (section 9) when it changes how records
   join or what a row is, before any build starts.
8. **Hand off** (the list above). Do not restate that skill's steps.

## Reviewing the model itself

Asked to review the model, check:

- **Overlapping types:** two relationship types with the same ends and the
  same meaning in their codes' definitions (`mdm-relationship-types`).
- **Inverse types without a note:** two types for one fact in opposite
  directions, which the definitions do not say are inverses.
- **Names that need their definition:** a type whose capacities its name
  alone does not describe.
- **Reference data outside RDM:** code lists a kind's fields or a contract
  carry with no code set behind them.
- **Code sets that cannot be checked:** a crosswalk to a code set RDM does not
  hold.
- **One kind split by identifier:** two contracts, targets or loads for one
  kind that differ only by the identifier asked; a source's rules that pair
  two identifiers of one master, or read another run to do it.
- **A key the data repeats:** a child table or record key whose values
  repeat in the captured data, or that rests on a column read from another.
- **A master in review for holding many values:** a kind whose Identifier
  Contract lets one master hold many values (`reverse` open) but whose
  masters are set to review when they do.

Report each with its evidence and the decision it needs; rulings are the
operator's.

## Examples

Examples only; nothing above depends on them.

- **Identity:** the company kind's Identifier Contract declares `cik`
  (`rules/merge/kinds/company.yaml`); its records join GLEIF's through the
  matching rules switched on in the policy. An EIN mapped by a contract's
  `cross_references` would be a cross-reference, lookup only (no contract maps
  one today).
- **One kind, many identifiers (ticket 138):** a CUSIP and an ISIN are two
  identifiers of one Security, not two kinds or two loads. An OpenFIGI answer
  has no CUSIP or ISIN field; the CUSIP answer and the ISIN answer of one
  security share their listing FIGIs, so the FIGI, matching in the
  Cross-reference, puts them on one master id. A ticker and exchange stays
  lookup only: 17,941 such pairs are on two or more CUSIPs (2026-10-15
  capture). The one table is built for Security first; the other kinds follow
  in their own tickets.
- **A grouping as a crosswalk:** the EDGAR place codes (`DE`, `X1`, `XX`)
  carry a `type` (US, CANADIAN, FOREIGN, UNKNOWN). Parent codes `US` and
  `FOREIGN` would make "FOREIGN" a valid state code, so `type` became its own
  code set, `sec-place-types`, with a `broad` crosswalk row from each place
  code; the ISO 3166 codes are `exact` rows to `iso-3166` (`outside`).
- **Real names (profiling ticket 04b):** the review of 2026-10-07 found
  `ACCOUNTING_PARENT` beside `IS_DIRECTLY_CONSOLIDATED_BY`, and
  `REPORTED_ULTIMATE_PARENT` beside `IS_ULTIMATELY_CONSOLIDATED_BY`: invented
  names for what GLEIF's relationship file already names. The operator kept
  GLEIF's two names, each link marked stated or calculated, and approved every
  other name one by one from its source: `BENEFICIAL_OWNER_OF` (13D/13G, Forms
  3/4/5), `IS_SUBSIDIARY_OF` (Exhibit 21), `INVESTMENT_ADVISER_TO` (Form ADV,
  N-CEN) beside GLEIF's `IS_FUND-MANAGED_BY` (a fund's manager, a different
  role), `HAS_MARKET_OPERATOR` (MiFID II's market operator),
  `SUCCESSOR_ENTITY` (GLEIF).
- **Who decides is not who owns:** an adviser's discretion (discretionary or
  non-discretionary, Form ADV Item 5.F) is on its link; ownership is
  `BENEFICIAL_OWNER_OF`.
- **The Security model (ticket 138, 2026-10-25): every rule above, measured.**
  Counts from the 2026-10-15 OpenFIGI capture and the 2026 Q2 N-PORT
  holdings; the security-master skill states the rulings.
  - *One kind, many identifiers.* OpenFIGI had been loaded as a CUSIP target
    and an ISIN target, the ISIN one reading the CUSIP runs, and N-PORT paired
    them again in seven steps. One target, one record per answer with every
    identifier, replaced them.
  - *The identifier's level.* A FIGI exists per trading line, per country
    (composite) and worldwide (share class). Of 380,047 ISIN answers, any
    shared listing FIGI pairs 350,867 with one CUSIP answer; the composite
    pairs 9,184 and the share class 9,032, because 343,236 of 353,491 CUSIP
    answers carry no composite. The listing FIGI matches; the other two are
    lookup only.
  - *Reading a clash.* 80 composite FIGIs sit on two or more CUSIPs: 71 with
    the same name and type, 9 different; share class 13 and 2. Ticker and
    exchange: 17,941 pairs on two or more CUSIPs (55,057 CUSIPs), so lookup
    only.
  - *Who may join.* 154 filed CUSIP and ISIN pairs (241 holdings) lead to two
    Securities; they bind by the CUSIP and merge nothing. 24,543 pairs have
    only one side known to OpenFIGI, so a filing adds the other identifier
    when no Security holds it.
  - *A child key.* "(master id, exchange code)" repeats: OpenFIGI gives a FIGI
    per trading line, and multi-currency venues carry a line per currency
    (90% of 292,567 same-venue groups have currency-suffixed tickers). The
    currency, read from the ticker, still repeats on 71,974 of 2,184,699
    lines, so the listing FIGI is the key and (master id, exchange, currency)
    an index.
  - *Proving it.* Apple (the common case), an ADR and its ordinary share
    (look-alikes that must stay apart: two Securities, one issuer), and a
    European stock (ISIN only) gave the same masters in all three load orders.
  - *A master fact from transaction rows.* N-PORT reports an asset category,
    issuer type, country and currency on each holding; the Security takes the
    most-reported value; the holding row in silver does not repeat it.
