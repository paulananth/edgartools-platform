# 141: Company, Person and Fund matched the way Security is

Priority: 141. Map: [Rebuild priorities](../map.md). Opened 2026-10-27 20:36 ET.

Type: grilling. Status: resolved (2026-11-04 14:33 ET) by the PR that carries this line: no change.
Blocked by: none. Comes from [138](138-one-security-mastering-by-cross-reference.md)'s
follow-up line (operator, 2026-10-25: "Security now, others next tickets": the
table and lookup serve every kind; Company, Person and Fund move in their own
tickets).

## Question

Ticket 138 made a Security's matching identifiers a list read through one
reader, with the lookup index, the Merge Stage and the master read taking any
number of values. A filer's copy of an identifier it does not issue is used
only to look up a master, never to create one (Design 5). For Company, Person
and Fund, which of those rules change what they master today, and which only
need the kind's rules to say so?

## What is known

- The engine names no kind: list identifiers, `reverse` on the Identifier
  Contract, `on_several: merge`, `consolidates`, `on_conflict: first` and the
  lookup-only fallback are rule data any kind may state.
- Company, Person and Fund identifiers state `reverse: 1` (one value per
  master), the limit the engine enforced before 138.
- The mdm-engineering skill says "A filer's copy of an identifier it does not
  issue is lookup only". No Company, Person or Fund rule has been checked
  against it.

## Parts

- [x] The audit (2026-11-04 14:05 ET, read from the rules and the Dataset Contracts, `rules/merge/kinds/*.yaml` and each source's `dataset_contracts`): **Company** holds four identifiers, each `forward 1, reverse 1`: `cik` (issued by SEC: `sec.company` and `sec.nport.registrant`, both file it as their identifier), `crd` (`iapd.adv.filings`), `bd_number` (`iapd.adv.custodians`) and `lei` (declared issued by `iapd.adv.custodians` and `gleif.level1`; filed as an identifier by those two). **Person** holds `cik` (`sec.submissions.person`, `sec.ownership.reporting_owner`). **Fund** holds `sec_series_id` and `lei`, both from `sec.nport.fund`. No cross-reference is declared for any of the three kinds: no source files a Company, Person or Fund identifier it does not issue, by the contracts' own lists. The one question the lists raise is the LEI: GLEIF and its operating units issue it, yet the policy names the ADV custodians (rule `iapd-adv-custodian-lei`, ticket 76) and the N-PORT fund series as issuing sources and each mints by it, where Design 5 says a filer's copy of an identifier it does not issue only finds. Counts of how many records a copy finds a master by are not measurable now: the running store holds no staged records, and `company-on` is stopped; every identifier is the issuing source's own, so the count of copies that find is zero by construction
  filers that copy one; measure how many records a copy finds a master by
  (counts only)
- [x] The decision (2026-11-04 14:33 ET, asked as one question, answer "No change, close 141 with the audit (Recommended)"): no identifier of Company, Person or Fund needs a list or a reverse above 1, and the custodian and fund-series LEI rules stay as ruled (ticket 76 and the Fund onboarding)
  above 1, with the operator, one question at a time
- [ ] ~~Rules changes, each off until a limited test and the operator's switch-on~~ not needed (2026-11-04 14:33 ET): the decision above changes no rule
- [x] Tests, review, PR and merge (2026-11-04 14:33 ET): ticket text only, so no test and no code to review; the PR that carries this line
- [x] Learning → skill: none (2026-11-04 14:33 ET); the audit is in this ticket
