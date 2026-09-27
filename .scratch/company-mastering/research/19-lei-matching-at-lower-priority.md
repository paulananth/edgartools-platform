# Research 19: matching on an LEI, below the name rules

Operator, 2026-09-26: "investigate using lei for matching in lower priority".
Measured 2026-09-26 20:00 ET. There were zero SEC requests and no new bronze
reads.

## Inputs (pinned)

- **The Company population and the name rules' result.**
  `cm08-coverage-2.jsonl`, sha256 `97e5d118…6509`. It is the coverage file
  that `08-parity.json` pins.
  - It covers 6,414 Account hold-back Companies.
  - Each Company has its name-rule outcome: 3,050 bind, 2,849 have no match
    and 515 are deferred.
  - Each Company also has SEC's own `lei`, from the ticket 08 bronze scan of
    2026-09-24 (the newest `submissions.json` per CIK).
- **GLEIF.** The 2026-09-11 16:00 UTC Golden Copy, in two local extracts:
  - `cm08-gleif-all.jsonl` (`e4e6fe8a…`), all Level 1 records;
  - `cm08-gleif-ra000665.jsonl` (`ec49a79d…`), the 32,093 records under
    SEC's registration authority `RA000665`.
- **Check digit.** Each LEI is checked with the production `lei` format
  (`adapters.FORMATS`, mod 97).

The extracts are outside the repo, in the session scratchpad and
`~/.local/share/edgartools/clean-mdm/research/`.

## 1. SEC's own LEI

Of 6,414 Companies, **10** state an LEI. **7** are valid. The other 3 are a
12-digit number, a phone number and `CR 415499`. No LEI is stated by two
Companies.

| Group | Companies | What it means |
|---|---:|---|
| Agrees with the name rules | 3 | General Mills, Aegon, LyondellBasell: the stated LEI is the LEI the name rules bound |
| Conflicts with the name rules | 0 | — |
| Reaches a Company the name rules miss | 4 | see below |

The four that the name rules miss all look like the right entity when read by
hand. This is not a labelled proof:

| SEC | GLEIF | Why the name rules missed it |
|---|---|---|
| Innate Pharma SA (Marseille 13009) | INNATE PHARMA, GENERAL, ACTIVE/ISSUED, Marseille 13009 | the legal form `SA` makes the names differ |
| CB Financial Services, Inc. (Carmichaels PA 15320) | same name, GENERAL, ACTIVE/ISSUED, legal address Carmichaels 15320, headquarters Washington 15301 | deferred: no jurisdiction or postal agreement (SEC gives no state of incorporation) |
| FORUM MARKETS Inc (Palm Beach FL) | FORUM MARKETS, INCORPORATED, GENERAL, ACTIVE/LAPSED, Wilmington DE; previously ETHZILLA CORPORATION | deferred: no jurisdiction or postal agreement |
| Nexxen International Ltd. (Tel Aviv) | legal name in Hebrew; transliterated NEXXEN INTERNATIONAL LTD, GENERAL, ACTIVE/LAPSED, Tel Aviv | the legal name is in Hebrew |

## 2. GLEIF's record naming the CIK (`RA000665`)

**10** Companies have a GLEIF record whose registration-authority entity ID
is their CIK. Ticket 08 found 57, but on an earlier and larger Company
population.

| Group | Companies | What it means |
|---|---:|---|
| Agrees with the name rules | 6 | Camden Property Trust, Farmer Mac, three Federal Home Loan Banks, Energy Services of America |
| Conflicts | 0 | — |
| Reaches a Company the name rules miss | 4 | poor targets, below |

The four extra Companies are poor targets:
- Cineverse points at CINEDIGM CORP, which GLEIF marks **DUPLICATE**.
- Brighthouse Life Insurance and Gulf Coast Ultra Deep Royalty Trust are
  GLEIF **FUND** records. The name rules deferred them on category, which is
  correct.
- Industrial Logistics Properties Trust is **LAPSED**, and its jurisdictions
  conflict.

## 3. Which bar applies

- **The proof-free identifier path does not apply.** Policy Q14 lets
  identifier-only binding activate through a verified Identifier Contract
  with no statistical proof. But:
  - SEC does not issue LEIs, and ticket 11 says a record adds only the
    identifiers its own source issues;
  - Q14 says "an LEI does not establish a CIK crosswalk merely because both
    values exist".

  So SEC's stated LEI is SEC's claim about another authority's identifier.
  GLEIF's `RA000665` entity ID is the same kind of claim in the other
  direction.
- **The 95% measured bar applies.** A rule on either claim is an SEC-to-GLEIF
  source binding, so the confidence bands (`company-policy.md`, accepted
  2026-09-24) apply: it acts automatically only at a one-sided 95% lower
  bound.
- **No rule on either claim can pass it with today's data.** With every pair
  correct, the Wilson lower bound is n / (n + 2.706):

| Correct pairs | Lower bound |
|---:|---:|
| 7 (every SEC-stated LEI a Company has) | 72.1% |
| 10 | 78.7% |
| 52 (the least that reaches 95%) | 95.05% |

- **Widening the population is an operator ruling, not a measurement.** The
  proof could be drawn from all 356 valid SEC-stated LEIs across every filer,
  not only Companies. Ticket 08 found that, where both claims exist, SEC's
  stated LEI and GLEIF's `RA000665` CIK disagree in 3 of 20 cases.

## 4. How "lower priority" would work in the engine

The engine already has an order.
- **Identifier rules come first.** The caller's decisions and the CIK
  identifier rules bind first.
- **Then `matching.propose`.** It runs the active name rules, and it skips any
  GLEIF record already bound: "a name match never re-binds"
  (`matching.py`, `propose`).
- **A lower-priority LEI rule** would be one more rule in the same family. It
  would run after the name rules and take only GLEIF records that are still
  unbound. It would read SEC's LEI as a *matching value*, the way the name
  rules read the Name Census LEI through `_LOOKUPS["census_lei"]`. It would
  never assert it as `lei`, which keeps ticket 11 and the operator's
  lookup-only decision.

It needs, in order:
1. The loader keeps SEC's `lei`. Today it drops it; silver has no column,
   and the Snowflake landing schema would change too.
2. The SEC contract maps it as a matching value (a new SEC version, needing
   approval).
3. A new fixed lookup in `matching._LOOKUPS`.
4. A proof at the 95% bar, then the operator's approval. Step 4 cannot pass
   on today's population (§3).

## 5. What a lower-priority LEI can do without a proof

- **Conflict check.** When a Company is bound (by the CIK rule or a name
  rule) and SEC's stated LEI names a *different* GLEIF record, send that
  Company to review. This creates no link, so it needs no precision proof.
  Today it would fire 0 times.
- **Corroboration.** Keep the agreement ("SEC's stated LEI agrees") in the
  binding's evidence. The 3 + 6 agreeing Companies above would carry it.

## Recommendation (for the operator; not a decision)

- **Do not build an LEI matching rule now.** Both claims together reach at
  most 8 Companies the name rules miss, 0.12% of 6,414. Only the 4 SEC-stated
  ones look right. None can reach the 95% bar on today's data.
- **Keep SEC's LEI lookup-only**, as decided on 2026-09-26. When the loader
  starts carrying it, also store it as a matching value, so that the conflict
  check (§5) can be added cheaply.
- **Reach the 4 missed Companies by fixing why the name rules miss them:** a
  legal-form suffix, a transliterated name, and a place test when SEC gives
  no state. That work belongs with the name rules, which have a proof.
- **Look again when the Fund kind starts.** 337 of the 356 valid SEC-stated
  LEIs belong to `other` filers, mostly funds, where an LEI route may have
  the numbers to be proven.
