# 138: One Security mastering, joined through the cross-reference

Priority: 138. Map: [Rebuild priorities](../map.md). Opened 2026-10-25 15:31 ET.

Type: task. Status: in progress (Claude, branch `claude/t138-one-openfigi-load`).
Blocked by: none. Replaces the two-target design of [120](120-switch-on-securities.md)'s
"OpenFIGI first" part; the rest of 120's load waits for this.

## Rulings (operator, 2026-10-25, about 15:15–15:31 ET)

- Asked why OpenFIGI loads as a CUSIP part and an ISIN part: "it does not
  matter what question you ask, i expect the cusip and isin is in diffrent
  fields and expecialy in the cross referecne there are unique identifiers for
  a security"; "why do you need to read cusip results in isin they are not
  related thay are not sequienceial they are parallel"; "secutiy is the kind
  cusip and isin are diffrant identifiers of the same securities".
- "there should be one processing with all the identifier and this is the
  first load all other loads will add data to the security fields".
- "N-PORT creates the Security, if it truly unique this is also true for 13F,
  first lookup if not exists then master".
- "what about cross refrence table".
- "mastering must create an unique id and the unique id joins with all the
  other tables cross refrence and silver".

- Shown the data model: "there should be on identifiers table,
  cross_refrence table must hold all the identifiers, ask more questions".
- Asked (2026-10-25, about 15:45 ET), each with the recommended answer chosen:
  a new CUSIP whose listing FIGIs an existing Security holds: "One Security,
  both CUSIPs"; the cross-reference's scope: "Every kind" (Company, Person,
  Fund and Security in one table); history: "Yes, dates and source" (each row
  its source, first and last seen); a FIGI filed by 13F or N-PORT: "Yes, any
  source's FIGI" (it matches like OpenFIGI's; one that leads elsewhere than
  the filed CUSIP goes to review).

- "no need for identifier table"; then, asked again: two Securities found to
  be one: "Oldest id survives"; silver: "master_id only" (each silver row
  carries the master id alone; filed identifiers are read from the
  cross-reference); lookup-only identifiers: "None: all match"; an identifier
  already held by another Security: "There is only one master for security
  clarify masters" (asked again in plain words, below). Measured for the
  "all match" answer (2026-10-25 15:55 ET, CUSIP answers): 18,534 tickers
  are given to two or more CUSIPs (55,898 CUSIPs touched); composite FIGI
  80 (60 CUSIPs); share-class FIGI 15 (31 CUSIPs).
- Asked in plain words (about 16:10 ET): a record whose CUSIP one Security
  holds and whose ISIN another holds: "Consolidate A and B automatically"
  (the oldest id survives). Ticker: "Ticker + exchange matches"; then, shown
  that 17,941 (ticker, exchange) pairs are given to two or more CUSIPs
  (55,057 CUSIPs, which automatic consolidation would merge): "Lookup only"
  (2026-10-25 16:18 ET). So every Security identifier matches except ticker
  and exchange, which only find.
- On the data model page, at the Listing table: "we don't need this table,
  cross reference should also be able to store ticker+exchange or ticker for
  lookup" (2026-10-25, about 16:40 ET). MDM keeps no listings detail rows
  for OpenFIGI (this replaces the 2026-10-20 "Detail rows set in config" use
  for listings); each listing stays in silver's `openfigi_listing`; the
  cross-reference holds each listing's FIGI (matching), its ticker and its
  ticker + exchange (lookup only).
- At the Security master: "must have name and all fields from openfigi for
  that security and any other unique fields from other sources". Found: of
  OpenFIGI's security fields, `securityDescription` reaches silver but not
  MDM; N-PORT files asset category, issuer type, investment country,
  currency, restricted and derivative category on each holding, in silver
  only. Asked: those N-PORT fields: "Most-filed value" (the value the most
  holdings file; a tie keeps none; each holding's value stays in silver); the
  security description: "Same rule as name" (the one value the listings
  state, else the US composite's, else the ISIN country's composite's).
- "am i missing anything also update the mastering process in the skills"
  (2026-10-25 19:51 ET). Asked, each with the recommended answer chosen: a
  wrong automatic consolidation: "Steward splits + exclusion" (a steward
  splits it, both ids return, a Match Exclusion stops the same records
  merging again; the Identifier Contract's tolerance still switches matching
  off); the other kinds: "Security now, others next tickets" (the table and
  lookup serve every kind; Company, Person and Fund move in their own
  tickets); Form 4: "Ticker within its issuer" (the ticker is looked up only
  among the Securities of the Form 4's issuer Company; one found attaches,
  none or two go to review; ticket 24); N-PORT's other identifiers: "SEDOL,
  CINS, LoanX match; Bloomberg ID lookup" (ticket 125).
- Asked to test it on Apple, one ADR and one European security (about 19:55
  ET), then: "cusip is a seperate than isin it can never be merges using+"
  (a filed CUSIP and ISIN never merge two Securities); a holding whose CUSIP
  and ISIN lead to two Securities: "bind by CUSIP if matches if not then try
  isin and try to bind"; is the filed other identifier added: "i assume that
  openfigi will have both cusip and isin they both must be in the cross
  reference" (read as: not added from a filing; OpenFIGI gives both); a
  filed pair neither of which is held: "Both" (mint with both); composite
  and share-class FIGI: "Lookup only" (2026-10-25 20:08 ET). So only the
  listing FIGI shows two Securities are one; "all match" is replaced.

## Spike on the real captures (2026-10-25 20:08 ET)

The decided rules in memory (`spike138.py`, scratchpad, not in the repo)
over the real OpenFIGI answers and the 2026 Q2 N-PORT holdings, three
securities picked at run time by shape, each in three orders (CUSIP answers
first, ISIN answers first, N-PORT first). Counts only:

| Case | Masters | Holds | N-PORT holdings |
|---|---|---|---|
| Apple | 1 | CUSIP, 301 listing FIGIs | 2,072 bind by CUSIP |
| An ADR and its ordinary share | 2, apart in every order | ADR: CUSIP, ISIN, 127 FIGIs; ordinary: ISIN, 165 FIGIs | 63 by CUSIP, 377 by ISIN |
| A European common stock | 1 | ISIN, 297 listing FIGIs | 418 bind by ISIN; 4 filed CUSIPs not added |

Every N-PORT filed CUSIP + ISIN pair (382,605 pairs, 3,518,266 holdings):
350,873 already one Security by OpenFIGI's FIGI; 24,543 with only one side
answered by OpenFIGI; 7,035 neither; 154 (241 holdings) would have merged
two Securities, which the 20:08 ruling now prevents. FIGI clashes: of 80
composite FIGIs on two or more CUSIPs, 71 same name and type, 9 differ; of
15 share-class FIGIs, 13 same, 2 differ.

Gap: OpenFIGI was asked Apple's CUSIP, not its ISIN, so Apple's Security
gets no ISIN unless N-PORT runs first (then it mints with both): the result
depends on the order for the 24,543 one-side pairs. Needs a ruling.

Ruling: "add idintifiers from other sources if not found in openfigi"; on
the data model page: "cusip or figi or isin for lookup" (13F), "use the same
language on all source steps". So every source does the same three steps:
look up CUSIP, then ISIN, then FIGI; bind to the first Security found and add
the record's other identifiers that no Security holds; none found, mint with
all its identifiers. A filing never moves an identifier and never merges two
Securities. Re-run: Apple 1 Security with CUSIP, ISIN and 301 FIGIs; the ADR
and its ordinary share 2 (the ordinary gains 3 filed CUSIPs); the European
stock 1 (4 filed CUSIPs added, 2 of them CINS, none answered by OpenFIGI);
every case the same in all three orders.

On the page, at 13F: "this should be second source, 4b"; asked whether that
also changes which value wins: "Load and priority" (2026-10-25 20:20 ET).
13F loads second, and Field Survivorship becomes OpenFIGI, then 13F, then
N-PORT, replacing the 2026-10-18 "make openfigi priority 1 and 13f last".
Measured then (ticket 84): N-PORT states one name for 62.4% of its 385,382
CUSIPs, 13F for 59.9% of 29,942.

On the page (2026-10-25 20:56 ET): "changing my mind need a separate table
for listing ie figi, exchange, ticker, exchange". The Listing table stays in
MDM: one row per listing FIGI with its exchange, ticker and composite FIGI,
on the Security's master id (the 2026-10-20 "Detail rows set in config"
table; this replaces "we don't need this table"). The listing FIGI still
matches through the Cross-reference; ticker and ticker + exchange stay
lookup only. Asked "do we have 1 issuer or ultimate parent issuer one equity
or 2": Apple is one Security (1 share-class FIGI), "issued by" one Company
by the issuer LEI N-PORT files (2,061 of 2,072 holdings file one LEI, 11
another); the ultimate parent is the Company's own parent chain, not the
Security's. The ADR and its ordinary share are two Securities with one
issuer (431 of 440 holdings file one LEI); the European stock 409 of 418.

The Listing key (2026-10-25 21:10 ET). Proposed on the page: "pk, (master
id, exchange code )". Measured: 17,081 answers hold two or more lines on one
exchange code (292,567 groups, mostly the EU, XV, XW, XO, XA, XG, XH, XF
venues); in 263,664 groups (90%) every ticker is one root plus a currency
code: OpenFIGI gives a FIGI per trading line, one per currency. Asked, "pk
can add currency code and make it unique"; measured, OpenFIGI states no
currency, and (master id, exchange, currency read from the ticker) still
repeats on 71,974 of 2,184,699 lines (7,392 securities). Ruling: "Listing
FIGI as key; exchange + currency as columns". The currency is read from the
ticker's suffix, blank where none, against a currency code set in RDM.

GoF consult on the build (2026-10-25 20:45 ET): extract one reader of a
record's identifiers (scalar or list) used at every site; make the conflict
outcome rule data (`on_conflict: review | first`, `on_several: review |
merge`) beside `on_no_match`. Found: `master_records.rs` sends a master with
two values of one identifier to review (`authoritative_identifier_conflict`),
whatever the contract's `reverse` claim says, so a Security with many FIGIs
or two CUSIPs would wait; the build reads `reverse`.

Overlap (operator, 2026-10-25: "Build the rest now, wait for #1171"):
Codex's draft #1171 changes `record_reads.py`, `record_lookups.rs`,
`store.py`, `merge.py`, the path a load takes. The planner, master records,
contract reader, rules and tests are built now; the holder lookup waits.

These replace, for Security: the 2026-10-14 "FIGI ... lookup only" ruling,
the 2026-09-26 "cross reference id for lookup ... only" ruling (the listing
FIGI now joins records; ticker, SEDOL stay lookup only), and ticket 120's
CUSIP-then-ISIN order (operator, 2026-10-23).

## Found (2026-10-25 15:30 ET)

FIGI work is split in three places today:

- OpenFIGI declares four targets over the same answer files: `answers_cusip`
  and `answers_isin` (read only for N-PORT), `mastering_cusip`, then
  `mastering_isin`, which reads every finished CUSIP run's FIGIs, so it waits.
- Two Dataset Contracts (`openfigi.security.v1`, `openfigi.security_isin.v2`)
  and three matching rules, one per kind asked.
- N-PORT Securities pairs CUSIPs with ISINs by FIGI again (`cusips_found`,
  `isins_found`, `figi_pairs`, `agree`, `offers`, `attach`, `fold`).
- Silver's `openfigi_listing` keeps two MDM id columns
  (`security_mdm_id_by_cusip`, `security_mdm_id_by_isin`), one per contract.

Root cause: a record carries one value per identifier kind, matching reads
only those, and the cross-reference is lookup only. An OpenFIGI answer holds
no CUSIP or ISIN field; the only thing a CUSIP answer and an ISIN answer of
one security share is their listing FIGIs. With FIGI unable to join, the
pairing was built in source rules, across runs.

Measured on the 2026-10-15 capture (353,491 CUSIP and 380,047 ISIN answers
found; counts only), how many ISIN answers pair with exactly one CUSIP answer:

| Shared FIGI used | one CUSIP | none | two or more |
|---|---|---|---|
| any listing FIGI | 350,867 | 29,169 | 11 |
| the lexically first listing FIGI only | 350,753 | 29,294 | 0 |
| any composite FIGI | 9,184 | 370,811 | 52 |
| any share-class FIGI | 9,032 | 370,988 | 27 |

343,236 CUSIP answers carry no composite FIGI, so composite and share class
cannot pair. One FIGI per record misses 114 pairs (two Securities for one
security); every listing FIGI misses none.

## Design

1. **Mastering mints the one id.** Each Security is one row of the master,
   with its master id (read through `current_entity` after a consolidation).
   The cross-reference and every silver row join on it; silver carries the
   master id only.
2. **The cross-reference is the one table of identifiers**, for every kind:
   master id, kind, identifier kind, value, matches or lookup only, source,
   first and last seen. No separate identifiers table. For Security, CUSIP,
   ISIN, listing FIGI, composite FIGI and share-class FIGI match; ticker and
   exchange are lookup only.
3. **A record carries every identifier it has** (lists allowed: every
   listing FIGI). Matching looks each one up: none found, a new master id;
   one Security, it joins; two Securities, they consolidate automatically and
   the oldest id survives, the other id pointing at it.
4. **OpenFIGI: one target, one Dataset Contract, one matching rule.** It
   reads `id_cusip/*` and `id_isin/*` together; its bundles run in parallel
   with no order. The ISIN target, `figi_ids`, `figi_cusips`, `attach`, and
   `answers_cusip` / `answers_isin` are deleted.
5. **Every other source looks up first, then masters** (N-PORT, 13F): its
   record joins the Security holding any of its identifiers, else creates it;
   a FIGI it files matches like OpenFIGI's. N-PORT's FIGI pairing chain is
   deleted.
6. **Silver** `openfigi_listing` keeps one master id column.

## Checklist

- [x] Rulings recorded, with the operator's words (2026-10-25 15:31 ET)
- [x] Measured the pairing on the capture (2026-10-25 15:30 ET): table above
- [x] Data model page (`.lavish/security-mastering.html`), reviewed with the operator in Lavish (2026-10-25 19:51 ET)
- [x] Skills say the decided process (security-master, data-modeling, mdm-engineering), marked decided, not built (2026-10-25 19:57 ET): skill tests 80 passed (genericity, role skills); architecture and skill commands 349 passed before the genericity fix
- [ ] Follow-up tickets: Company, Person, Fund onto the one cross-reference; steward split with a Match Exclusion
- [x] GoF consult on matching and binding (2026-10-25 20:45 ET): one identifier reader; conflict outcomes as rule data; `master_records.rs` reads `reverse`
- [ ] Engine: a record's identifier may be a list; matching and binding look up each value; one Security joins, two go to review
- [ ] Rules: OpenFIGI one target and one contract (`openfigi.security.v3`), every listing FIGI as identifier `figi`; Security kind declares `figi`; one OpenFIGI matching rule
- [ ] Rules: N-PORT's FIGI pairing chain removed; N-PORT and 13F join by any identifier, else create
- [ ] Silver: `openfigi_listing` one MDM id column
- [ ] Listing table in MDM keyed by the listing FIGI: master id, exchange code, currency (from the ticker suffix, RDM currency codes), ticker, composite FIGI; indexed (master id, exchange code, currency)
- [ ] Two bundles minting one Security at once: the second re-checks every identifier under the lock and binds
- [ ] Holder lookup on the load's path (`record_reads.py`, `record_lookups.rs`) after #1171 merges
- [ ] `rules/source-sequence.yaml`: no OpenFIGI order inside the source
- [ ] Tests: list identifiers join, create, review; every changed rules file's tests
- [ ] Three-axis review
- [ ] PR, CI green, merge
- [ ] Proof on the capture: counts, no identifier on two Securities, a second pass changes nothing
- [ ] 120's load in `working`
- [ ] Learning → skill
