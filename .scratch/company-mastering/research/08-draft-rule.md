# Ticket 08, step 2: a stricter SEC-to-GLEIF matching rule (draft)

Measured 2026-09-25 14:20 ET. Zero SEC and GLEIF requests. These are
development and coverage numbers; they tune the rule, they do not qualify it.

## Step 1 re-based on the Account hold-back

The SEC Company population is now 6,414 filers (5,278 at step 8, 1,136 at
step 10; `08-companies.py`). The step-1 finding holds: SEC states its own
LEI for **10** of them, and GLEIF authority `RA000665` covers **10**. Neither
joins the Apple, Microsoft, Shell or ASML records.

## What made the old comparison fail

On the 883 reviewed pairs (`08-dev-levers.py`), the earlier strong tier (B)
was right 207 times out of 214, a lower bound of 0.941. Most of its misses
were a **dropped legal form**: it cut "INC", "LLC" and "LP" off both names
before comparing, so it matched:
- "Wayfair Inc." with "WAYFAIR LLC";
- "ADT Inc." with "ADT LLC";
- "COUSINS PROPERTIES INC" with "COUSINS PROPERTIES LP".

In each pair they're two legal persons, a parent and its subsidiary or an
operating partnership.

Kept form. The SEC name and the GLEIF legal name are compared with the legal
form kept. The spellings are unified first: CORPORATION becomes CORP,
COMPANY becomes CO, "L.L.C." becomes LLC, and SEC's "/DE/" tag and a
leading "THE" are dropped. On that basis:

| Development rule | Links | Same entity | Lower bound (95%) |
| --- | ---: | ---: | ---: |
| earlier tier B | 214 | 207 | 0.941 |
| kept form + jurisdiction agrees | 234 | 232 | 0.975 |
| kept form + headquarters postal agrees | 154 | 154 | 0.983 |
| kept form + (jurisdiction or postal agrees) | 254 | 252 | 0.976 |

The two misses under the last rule are `unresolved` readings: a renamed SPAC
under its old name, and a possible conversion. Neither was read as a
different entity.

## Two faults in the old comparison, fixed

- SEC writes a US state code where a country belongs (`country: "MI"`). A
  state code now means the United States.
- A registered agent's address is no evidence. Examples are 1209 Orange St,
  Wilmington, where GLEIF's legal address names "C/O The Corporation Trust
  Company", and Ugland House. Only GLEIF's headquarters address is compared.

## The draft rule over the whole population

The draft rule (`08-coverage.py`), in order:
1. The current SEC name and the GLEIF legal name are equal with the legal
   form kept.
2. Across the **whole pinned GLEIF publication** (3,428,477 records), exactly
   one legal entity carries that name, counting its legal **and other**
   names. Branches are not counted: a branch carries its head office's name
   and isn't a legal entity.
3. That entity is GENERAL and ACTIVE, and not DUPLICATE or ANNULLED. An
   INACTIVE entity has ceased while its SEC filer still files, which the
   labelling standard reads as unresolved.
4. Among **all 76,230** SEC filers, exactly one has carried that name,
   counting current **and former** names.
5. It binds on **jurisdiction** when SEC's state or country of incorporation
   (mapped to ISO, `08-edgar-codes.json`) agrees with GLEIF's legal
   jurisdiction.
6. Otherwise it binds on **postal code** when SEC's business postal code and
   GLEIF's headquarters postal code agree, in the same country.

| Outcome over the 6,414 Companies | Count |
| --- | ---: |
| binds on jurisdiction | 2,855 |
| binds on postal code | 264 |
| no GLEIF record with this name | 2,849 |
| waits: neither jurisdiction nor postal agrees | 248 |
| waits: the name names several GLEIF entities | 103 |
| waits: another GLEIF entity has the name as another name | 55 |
| waits: the name names several SEC filers | 27 |
| waits: GLEIF entity INACTIVE | 7 |
| waits: GLEIF category FUND (4) or government (2) | 6 |

**3,119 Companies (48.6%) bind.** Counting every name for uniqueness held
back 65 that the current-name-only count had let bind, and INACTIVE held back
7 more. Apple and Microsoft bind on jurisdiction.
Shell and ASML bind on postal code, because SEC holds no usable state of
incorporation for them:
- Shell's is "DC";
- ASML's is empty.

Each of the four binds to the LEI the operator picked for the four-company
test.

Two SEC formatting details the postal comparison allows for:
- A foreign address carries its country in `countryCode` (Shell: `X0`), not
  in `stateOrCountry`.
- SEC keeps only the digits of a Dutch postal code ("5504" for GLEIF's
  "5504DR"). Only that shape agrees on a prefix: four digits against four
  digits and two letters, in the Netherlands. This allowance was written
  after reading ASML, so ASML, the other three test Companies and all 1,000
  development CIKs are left out of the qualification draw.

## What the Stage needs for this rule

- **Jurisdiction step:** SEC `state_of_incorporation` and GLEIF
  `jurisdiction`, both already mapped.
- **Postal step:** the SEC business address, which the SEC adapter doesn't
  read yet. It becomes pinned evidence (`sec_company_address`), as ticket 12
  did with tickers and forms.
- **Uniqueness:** counts over the whole GLEIF publication and every SEC filer.
  A Stage holds a bounded scope, so these counts can't come from Stage rows;
  they must be pinned evidence the rule reads. That design is written up in
  the ticket.

## Files and hashes (outputs kept outside the repo)

| Output | sha256 |
| --- | --- |
| `cm08-companies.jsonl` (6,414) | `2a57faa7…d3731` |
| `cm08-coverage.jsonl` (6,414) | `3b51d0ac…5e1f698` |
| `cm08-gleif-all.jsonl` (3,428,477) | `e4e6fe8a…1d9f` |
| `cm08-sec-scan.jsonl` (76,230) | `bdf379bf…c0d1` |
