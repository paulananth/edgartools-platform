# Which SEC filers the Company classification rule may call a Company, measured

Ticket: 12. Run 2026-09-24, 19:40–20:22 ET. Bronze only; zero SEC requests.

## Result

`sec-company-candidate` version **2026-09-24.6**, verdict `company`:

| | n | correct | one-sided 95% Wilson lower bound |
|---|---|---|---|
| All `company` verdicts | 300 | 297 | **0.97524** |
| step 2 (`operating`) | 229 | 227 | 0.97395 |
| step 4 (`other`, industry code, legal-form word) | 71 | 70 | 0.93931 |

The Company classification bar is 0.95 at 95% one-sided confidence (confidence
bands, `docs/specs/clean-mdm/company-policy.md`). The verdict clears it.
Activation is per verdict, not per step (§9); step 4 alone does not clear
0.95 on 71 records, and is reported so the operator sees it.

Adversarial fixture: **294 records, 0 violations** — 100 individuals with no
industry code, 100 SEC `investment` funds, and every individual SEC gave an
industry code (94; the case a bare "has a SIC" test fails on).

The three errors, all private funds typed `operating` or `other`:
`VELOCE CAP FUND 1 LP`, `Blackstone Private Equity Strategies Fund L.P.`, and
`KKR Private Equity Conglomerate LLC` (uncertain; counted as an error).

## The rule

1. industry code 6189 (asset-backed trusts), 6221 (exchange-traded commodity
   and crypto trusts, futures pools) or 8888 (foreign governments) → wait
2. `entity_type = operating` → Company
3. `other` and a person's suffix in the name (JR, SR, ESQ, …) → wait
4. `other`, an industry code, and a legal-form word in the name → Company
5. otherwise → wait

On all 76,230 bronze filers: 8,254 Company (5,980 by step 2, 2,274 by step 4),
67,976 wait. Apple, Microsoft (step 2), Shell, ASML (step 4) are Companies;
Tim Cook and Satya Nadella wait.

## Operator decisions this rests on (2026-09-24)

- An SEC `investment` filer is a **Fund** (all 1,793 file fund forms).
- A business development company (BDC) is a **Company**.
- An asset-backed loan trust is **not a Company** (1,040; SIC 6189).
- An exchange-traded commodity or crypto trust, or a futures pool, is a
  **Fund** (about 150; SIC 6221).
- A foreign government is a Government Body, not a Company (`CONTEXT.md`).

## Method

- **Population**: the newest bronze `submissions.json` per CIK, summarised by
  `.scratch/individual-filer-company-misclassification/research/05-scan-bronze-entity-types.py`
  (SHA-256 of the summary in `12-population.json`; the 28 MB file itself is
  not committed).
- **The rule is run by the engine** (`classification.fired`) from
  `edgar_warehouse/mdm/policies/company.json`, so the number measures the code
  that runs.
- **Sample**: simple random, 300 of the 8,254 `company` verdicts, seed
  `20260924.6`. Three earlier draws (seeds `20260924`, `20260924.4`,
  `20260924.5`) each shaped the next rule version — they found the people,
  loan trusts, governments and exchange-traded trusts — so none of them
  measures this version.
- **Labels** come from evidence the rule does not read first: forms filed,
  tickers, exchanges, filer category; the name only when none decides. Every
  draft that was not a plain Company, and every fund-, trust- or
  partnership-looking name, was then read by hand against its forms
  (`final`, `note` in `12-sample.jsonl`). Labels are my reading, not an
  external authority, as in research 18.
- **Rule changes found by the adversarial arm, not the sample**: step 3 exists
  for `HOLDING FRANK B JR`, a person whose surname is a legal-form word.

## Files

`12-classify.py` (`sample`, `score`; sockets blocked), `12-sample.jsonl`,
`12-adversarial.jsonl`, `12-population.json`, `12-summary.json` (every count
above and each file's SHA-256).

## What this does not establish

It is not activation: that is the operator's approval of one exact policy
digest (ticket 06). It says nothing about SEC-to-GLEIF matching (ticket 08),
nor about records that wait: a waiting record is not an error, it is held for
a later rule (Fund kind, Government Body kind).
