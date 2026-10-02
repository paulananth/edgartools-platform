# Rewrite SEC-to-GLEIF matching as priority name-and-address passes

Type: research, then build
Status: resolved: the passes are built and switched off (#746); the remaining labelling and switch-on moved to `mastering-to-done/issues/07-cascade-passes-switch-on.md` (2026-10-02 audit, mastering to-do 01).
Was: in progress
Blocked by: nothing. Ticket 22 (data quality) merged 2026-09-28 09:50 ET (#742).

Operator ruling, 2026-09-27, after the research and three measured designs:
"need data quality checks before merge, dq will be a seperate rule, finally
cascade merge". So this ticket builds the operator's cascade, on the values
ticket 22's quality rule leaves fit to use.

## Question

Operator, 2026-09-27: "re write the matching logic using priority, name and
address first, it it matches merge it, no need to match on jurisdiction
/research how to impliment priority mergeing, you merge with all fields first
then you reduce the fields gradually until you get more mergeing".

This replaces the two jurisdiction and postcode rules of ticket 08, and the
"/DE" and Wilmington fixes the operator asked for earlier the same day
(ruling: a Wilmington seat binds only when SEC agrees or is silent).

## Checklist (times ET)

- [x] Research note on cascade matching started (2026-09-27 19:50 ET):
  [research 21](../research/21-priority-matching.md).
- [x] Measure a pass ladder on the ticket 08 inputs (20:00 ET):
  [`21-tiers.py`](../research/21-tiers.py), result
  [`21-tiers.json`](../research/21-tiers.json).
- [x] Read the research note; settle the pass ladder and its safeguards
  (operator rulings 2026-09-28: no veto, the proof decides; the approved
  rules stay until ticket 20).
- [x] Put the result and the open question to the operator.
- [x] `/gof-refactor-reviewer`: leave the structure; `PAIR_TESTS` is the
  registry new tests join.
- [x] Built the passes as rules data and the engine that runs them, switched
  off; measured through the production function (above).
- [x] Three-axis review (2026-09-28). Fixed:
  - Standards: `normalize` reads fields, relationships, then matching
    values and quality in its old order, so a record set aside keeps its
    reason; activating the measured rules still fails closed on a missing
    proof; the passes together are checked in `check_policy` (distinct, one
    threshold); the "not unique" flag is renamed to what it counts ("name
    held by another candidate").
  - Spec: the census runs the cascade only once a pass is switched on, so
    until ticket 20 the census and every SEC record are as before; a pair a
    rule refuses by flag goes to a Steward (`cascade_flagged_pair`), not to
    a bind; the proof now reads filers and entities through the census's own
    readers (`cascade_filer`, `cascade_entity`), not a copy.
  - GoF: leave the structure; the Stage re-check reads the GLEIF place
    directly.
- [ ] Draw and label a sample per pass × stratum (clean, incorporation
  conflicts, name held by another candidate), from the links each pass adds,
  with an adversarial arm (conflict pairs, shared headquarters) and fresh
  draws for P5 to P7; prove each cell at the 95% bar (52 correct links at
  least). A cell short of that stays off; its pairs go to a Steward.
- [ ] Three-axis review, PR, CI; merge on the operator's word.

## Measured (2026-09-27 20:00 ET)

Inputs: `cm08-coverage-2.jsonl` (`97e5d118…`, the 6,414 Companies), all
76,230 SEC filers (`cm08-sec-scan.jsonl`) and all 3,428,477 GLEIF records of
the 2026-09-11 16:00 UTC Golden Copy (`cm08-gleif-all.jsonl`).

Each pass takes only what is still unmatched and binds a pair only one to
one. Names are equal with the legal form kept, counting GLEIF's other names.
The GLEIF entity is GENERAL, ACTIVE, not DUPLICATE or ANNULLED. A registered
agent's address gives only its country.

| Pass | Companies bound |
|---|---:|
| P1 name + street + city + postcode | 1,463 |
| P2 name + street + postcode | 90 |
| P3 name + street + city | 109 |
| P4 name + postcode | 424 |
| P5 name + city | 281 |
| P6 name + country | 1,036 |
| P7 name alone | 181 |
| **All passes** | **3,584** |

Today's two rules bind 3,050. The passes keep 3,048 of them, with the same
LEI, and add 536: 456 that wait today, and 80 that today find no GLEIF
record, through GLEIF's other names (Canon, Hitachi, Sony, Nokia).

## Measured with the quality rule, through the production function (2026-09-28 21:09 ET)

[`21-cascade.py`](../research/21-cascade.py) runs the passes through
`edgar_warehouse/mdm/clean/cascade.py` (`assign`), the function the Name
Census runs, so the numbers are what the engine would do. Result:
[`21-cascade.json`](../research/21-cascade.json), pairs in
`21-cascade.bound.jsonl`.

Inputs, rebuilt 2026-09-28 from S3 bronze (the originals were in a cleared
scratchpad; zero SEC requests), under
`~/.local/share/edgartools/clean-mdm/research/rebuilt-2026-09-28/`:
- `cm08-sec-scan.jsonl`: 76,230 filers, sha256 `030245b4…` (the original
  `bdf379bf…` is gone; newer bronze has landed since);
- `cm08-companies.jsonl`: **byte-identical** to the original, `2a57faa7…d3731`;
- `cm08-coverage.jsonl`: **byte-identical** to `cm08-coverage-2.jsonl`,
  `97e5d118…`, so "against today" compares as before;
- the ticker catalog, `836140c5…`, as ticket 12 pinned.
The Company list was rebuilt with a one-line import fix to `12-classify.py`
(`edgar_warehouse.mdm.policies` is gone; the rules now load from `rules/`).
That file is pinned by ticket 12's approved proof, so the fix was not kept.

| Pass | Companies | Clean | Incorporation conflicts | Name held by another candidate | Both |
|---|---:|---:|---:|---:|---:|
| P1 name + street + city + postcode | 1,251 | 1,187 | 39 | 24 | 1 |
| P2 name + street + postcode | 84 | 79 | 2 | 2 | 1 |
| P3 name + street + city | 101 | 94 | 1 | 5 | 1 |
| P4 name + postcode | 441 | 410 | 22 | 9 | 0 |
| P5 name + city | 242 | 224 | 12 | 6 | 0 |
| P6 name + country | 1,230 | 1,159 | 58 | 9 | 4 |
| P7 name alone | 235 | 221 | 14 | 0 | 0 |
| **All** | **3,584** | **3,374** | **148** | **55** | **7** |

- 3,801 addresses are over-shared (more than 25 entities), so they're compared by country only.
- Against today's two rules, the cascade keeps 3,048 of their 3,050 binds, all with the same LEI; it binds none to a different LEI and leaves 2.
- It adds 536 Companies:
  - 456 that wait today;
  - 80 with no GLEIF record of their legal name, found through GLEIF's other names.
- Ticket 08's labels, where a labelled pair falls in a pass:
  - P1: 747 same, 1 different (AAON), 13 unresolved;
  - P2: 65 same;
  - P3: 10 same;
  - P4: 263 same, 8 unresolved;
  - P5: 38 same;
  - P6: 285 same, 2 unresolved;
  - P7: 81 same.

  These were drawn from today's binds, not from what each pass adds, so they are not the proof.

Re-run through the census's own readers (`cascade_filer`,
`cascade_entity`, the passes from the Company rules), 2026-09-28 23:41 ET: the same
3,584 pairs, each with the same LEI and pass, and the same counts per pass
and stratum as above. The proof and the census read alike. Merged as #746
(`163ac301`, 2026-09-28 22:14 ET).

## Built (switched off)

- `cascade.py`: the passes (`assign`), the fit address, the readers of a
  Stage record (`filer_of`, `entity_of`), the passes read from the rules
  (`spec`).
- The Name Census runs the cascade over both whole sources when the Company
  rules declare passes, and pins the SEC address member it read; each SEC
  record carries its CIK's answer inside its census entry
  (`matching.name_census.cascade`), so the SEC contract is unchanged.
- `adapters.mapped_values`: the part of `normalize` that maps fields and
  matching values and applies quality, which the census reads every filer
  and entity through, so the two cannot differ.
- `cascade_pass@1`: the Merge Stage re-checks a pair on its own rows (the
  same LEI, last update, name key, no refused flag, the pass's address parts
  agree). A pass rule is checked for exactly one pass, eligibility and the
  one-LEI veto.
- `rules/merge/kinds/company.yaml`: seven rules `sec-gleif-cascade-p1..p7`,
  declared, not switched on. Without them the policy digest is the approved
  one (`3520e890…`; `983352e8…4049` without the place-code table).

## Open

- **AAON, Inc.** passes P1, and is wrong: GLEIF's AAON is the Oklahoma
  subsidiary of SEC's Nevada parent, at the same address. Only jurisdiction
  told them apart. Ticket 08's labels also hold 23 "unresolved" pairs the
  passes would bind, each with SEC and GLEIF naming different states (Hyatt:
  SEC Illinois, GLEIF Delaware).
- P5 to P7 have few labelled pairs (49, 181, 66), all drawn from today's
  binds; each pass needs its own draw.

## Decided: a conflict in place of incorporation (operator, 2026-09-28 19:49 ET)

Asked whether a pass should refuse a pair when SEC's state of incorporation
and GLEIF's jurisdiction differ (the AAON case), the operator answered "They
both may be true Hyatt (SEC says Illinois, GLEIF says Delaware)". GLEIF's
Hyatt Hotels Corporation (T27JQIMTYSH41TCD5186) is US-DE, so SEC's Illinois
is likely stale: the same company. GLEIF's only "AAON, INC."
(549300ZHF0E5VM7PUD37) is US-OK, and ticket 08's labels found it the
subsidiary: nothing in the pair itself tells the two cases apart.

Ruling ("Yes" to the recommendation): **no veto; the proof decides.** A pair
whose places of incorporation conflict goes through the passes like any
other and is its own labelled stratum. If that stratum clears the 95% bar
it binds; if not, those pairs go to a Steward for review.

## Decided: the approved rules stay until ticket 20 (operator, 2026-09-28 20:27 ET)

The two matching rules in use (Name-and-state, Postcode) carry the approved
fingerprint `983352e8…4049`. Asked whether this ticket may leave them in
place, the passes added switched off, the operator answered "Yes". Ticket 20
swaps them in one step, on the passes' proof and a new approval.

Design (advisor review, 2026-09-28): the cascade is decided once, over both
whole sources, by one production function a new Name Census version carries
per CIK (the LEI, its pass, its flags); the Merge Stage re-checks the pair
on its own rows. The proof calls the same function, so it measures what runs.

## Decided with ticket 22 (operator, 2026-09-28)

- **Addresses:** a pass compares the address the quality rule left fit:
  GLEIF's headquarters address first (`matching.headquarters_address`),
  else its legal address (`matching.address`); SEC's business address
  (`matching.address`). A withheld address is never compared.
- **Over-shared address threshold: 25** ("25, yes", 09:50 ET). An address
  (standardized street, 5-digit postcode, country) that more than 25
  entities use is not compared by any pass: 3,604 addresses, 271,352 GLEIF
  entities, on the ticket 08 inputs
  ([ticket 22 proof](../research/22-quality-proving-run.json)). It is a
  check across records, so it sits with the Company merge rules.
