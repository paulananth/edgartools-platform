# Fix three name-normalizer defects before Tier B activates

Type: task
Status: resolved (2026-09-21) — code on `claude/person-ticket-25`; Tier B activation must use it
Blocked by: none — ships **with** Tier B activation

## Resolution

There was no production normalizer to repair: the only running one was
research 17's (`research/17-common.py`), and Clean MDM's Person consumer is not
built. So the repaired normalizer is now production code, where that consumer
can import it: **`edgar_warehouse/domain/policy/person_name.py`,
`person-name@v2`**. It is made of pure functions with no I/O:

- `parse_conformed` reads EDGAR `LAST FIRST MIDDLE` names (Form 3/4/5
  `owner_name_raw`).
- `parse_western` reads free text (8-K, DEF 14A).
- `is_person_name_candidate` is free-text eligibility.
- `PersonName.key_mi` and `.generational` feed ticket 20's key and its suffix
  veto.

It sits outside `edgar_warehouse/mdm/clean/`, which is Codex's code, on
purpose. The handover note asks Codex to import it.

| Defect | Fix | Regression cases |
|---|---|---|
| 1. Multi-word surname | A particle (`DI`, `DE`, `VAN` …) joins the surname. In conformed form it joins through the token after the particle run, as long as a token is left for the given name; in western form the surname extends leftward from the last token. A particle *leading* the given name joins the next token in both forms ("LA VONDA"). `DAS`, `DO`, `DU` and `LE` are common standalone surnames (Indian, Chinese, Vietnamese), so they join a surname only in the middle of a name and never start a surname or a given name. | the Zegna brothers, `Bodin de Moraes`, `Gomide de Faria`, `Foufopoulos - De Ridder`, `DE LA HOYA`, `van Beethoven`, `de la Cruz`, `La Vonda Williams` ↔ `Williams La Vonda`, `DAS MANUVIR` ↔ `Manuvir Das`, `DU WEI`, `LE TRUC THANH`, `DO CUONG V`, `SANTOS DO CARMO` |
| 2. `V` as a suffix | The generational set is exactly ticket 20's `JR`/`SR`/`II`/`III`/`IV`. Credentials (`CFA`, `PHD` …) are suffixes but never a veto. `DO` is no longer a credential (Vietnamese surname). | `CRAWFORD MATTHEW V`, `Mark V. Anquillare`, `Stuart V. Flavin III`, `Anh Do` |
| 3. Eligibility | `DATE` and `BANK` added to the non-person vocabulary. It applies to free-text sources only; a Form 3/4/5 owner is classified by rule C-J, so `DATE RAJEEV V` keeps its key. | `Effective Date`, `Manufacturers Bank` |

Conformed names also drop `MR`/`MRS`/`MS`/`DR` (`Akbari Dr. Homaira`,
`PRICE BILLY L JR DR`). 52 unit tests (`tests/unit/test_person_name.py`).

**Research 21's census, re-scored** (`research/25-rescore.py` and
`research/25-rescore.json`, against `r17/records.parquet` sha256
`a88ee20d…2dc9f`). v1, read from that table, is the control and reproduces
research 21's headline exactly: 661 candidates, n = 659, LCB97.5 0.99420 /
0.99146.

| | v1 | v2 |
|---|---|---|
| Form 3/4/5 same-issuer homonym CIK pairs the fixed key merges | 1 of 11 (Zegna) | **0 of 11** (also 0 when the pairs are re-enumerated under v2) |
| ineligible rows reaching the key | 2 | **0** |
| middle initials lost to `V` (8-K / Form 3/4/5, v1-shaped records) | 7 / 241 | **0 / 0** |
| given name parsed as a particle token (8-K / Form 3/4/5) | 18 / 105 | **0 / 9**: `Tang Le` ×4 and `Narayandas Das` are real one-token given names; `Uang Du-Tsuen` ×4 is a hyphenated given name, split the same way in both forms |
| Form 3/4/5 records whose shape (key eligibility) changes | — | **0 lost, 1 gained** (`DO CUONG V`, which v1 mis-parsed) |
| 8-K eligible records | 4,193 | 4,147 (46 dropped: banks, dates, and particle surnames that have only an honorific, such as `Mr. Van Vleet`; `Van Dore` may be a given name + surname; 0 gained) |
| precision, optimistic / conservative | 1.0 / 0.99848 | **1.0 / 0.99848** |
| n; LCB97.5 optimistic / conservative | 659; 0.99420 / 0.99146 | 656; 0.99418 / **0.99142** |
| recall (of 934 labelled `same`) | 0.7045 | 0.7013 |

Research 21 counted "particle as given name" as 19 / 79 over all 7,878 /
72,981 records, using its narrower particle list. The row above recounts v1
with v2's list over the v1-shaped records, so the two figures differ.

**Verdict on "unchanged or better":**
- Precision is unchanged.
- Every defect count is better.
- The bound and recall move down by three pairs. Each of the three is a v1
  match that ticket 20 Q3's key does not permit:
  - A middle initial present on one side only is not a match ("absent-on-both
    matches"). This covers `Daniel Leff` / `LEFF DANIEL V` and `David Barry` /
    `Barry David V.`; v1 matched them only by discarding the `V`.
  - A key needs a given name. `Mr. van Tilburg` matched on surname alone.

So v2 applies ticket 20's key as written, where v1 over-matched. LCB97.5 stays
clear of 99% (0.99142).

The first cut of v2 read `DAS MANUVIR` and ten other Form 3/4/5 owners as a
surname with no given name. The review's Standards axis caught it, and the
"shape change" row above is the measurement that now guards it.

**Also:** `V` is removed from the Mastering Policy prototype's `person_suffix`
list (`.scratch/mastering-policy-language/prototype/policy-person.json`). Rule
C-J still reproduces research 18 there (841/841, 353/353, 26 deferred), and
the demo is rebuilt.

**Known limits** are listed in the module's docstring. They include a
conformed multi-token surname *without* a particle, hyphenated conformed
surnames, and Vietnamese "Van" as a middle name, all unchanged from v1 or
absent from the census.

**Review (three axes):**
- **GoF:** no structural finding. The lists stay in Python until a policy
  interpreter exists to feed them. It flagged `DO` being on two lists.
- **Standards:** one blocking finding, the leading-particle rule swallowing
  two-token names (fixed, with a shape-change measurement). Should-fix items,
  all done:
  - `DO` on two lists
  - conformed eligibility is C-J's job, not this module's (documented)
  - `V` counted as 242 vs 241 (population aligned)
  - known limits and a `PersonName` docstring
- **Spec:** one blocking finding, the re-score being stale against the final
  code (re-run; every figure here comes from the final JSON). Should-fix
  items, all done:
  - the verdict's reasoning
  - gate-bearing figures in consumer.md restated for v2
  - handover vocabulary aligned with the policy language
  - titles in conformed names
  - consumer.md's name-reorder row points here

## Question

Nothing to decide. [Research 21](../research/21-tier-b-8k-extended-labelling.md)
cleared Tier B for 8-K and, in doing so, measured three defects in the name
normalization the key depends on. None is a defect in the key itself
([ticket 20](20-redecide-tier-b-after-calibration.md) Q3 stands unchanged);
all three are in the primitive that parses a name into surname, given name and
middle initial, so they belong to the Mastering Policy's `name_shape`
normalizer rather than to the tier.

1. **Multi-word surnames are mis-parsed.** An EDGAR `LAST FIRST MIDDLE` name
   whose surname carries a particle or is multi-token ("Zegna" brothers) has
   the particle read as the given name. Measured: 0.453% of 8-K and 0.108% of
   Form 3/4/5 records. This is the single false merge the fixed key makes
   against Form 3/4/5's 11 same-issuer homonym CIK pairs — repairing it takes
   that key from 1-of-11 wrong to **0-of-11**.
2. **`V` is treated as a generational suffix.** It discards the middle
   initial of **241** Form 3/4/5 and **7** 8-K records whose middle name is
   simply "V". Drop `V` from the suffix token set; ticket 20's own token list
   (`JR`/`SR`/`II`/`III`/`IV`) is already the correct one and does not include
   it.
3. **Two non-person rows reach the eligible population.** `DATE` and `BANK`
   are missing from the eligibility vocabulary — one of them,
   `Manufacturers Bank`, research 17 had labelled `same`.

Resolved when each is fixed with a regression case and the research 21 census
re-scores unchanged or better.
