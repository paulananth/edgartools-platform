# Which reporting-owner classification rule reaches 99% precision (Form 3/4/5 -> person vs entity)

Ticket: 18. Run 2026-09-20.
Bronze only (prod S3, account 690839588395, `us-east-1`); no Snowflake, no SEC fetch by this
measurement (F9 covers what the repo parser itself fetches). Every number
below is reproducible from the four sibling files with `18-classify.py`; `18-summary.json` carries the
SHA-256 of `18-owners.jsonl` and `18-sample.jsonl`, and `18-extension-summary.json` that of
`18-extension-sample.jsonl` (computed last, after all writes). Labels are **my
own reading** of the owner name, the owner CIK's `submissions.json` fields and the filing text -- not
an external authority; every case I was unsure about is listed in F6.

## Sources read

Bronze (S3, `s3://edgartools-prod-bronze-690839588395/warehouse/bronze/`):
- `filing_artifact/<sha256>` -- 5,356 objects, 109,244,008 bytes, all synced. Every one is a full SEC
  `.txt` submission (SGML header + one `<ownershipDocument>` inside `<XML>...</XML>`); 0 non-ownership
  objects, 0 parse failures. The key is `f"{source_family}/{raw_evidence_hash}"`
  (`edgar_warehouse/acquisition/silver_acceptance.py:79-93`; hash = SHA-256 of the raw bytes,
  `acquisition/evidence_import.py:130-139`).
- `submissions/sec/cik=<cik>/main/<yyyy>/<mm>/<dd>/CIK<10>.json` (layout
  `edgar_warehouse/config/warehouse_paths.properties:13`; `pagination/` siblings at `:14`) -- 204,345
  objects under 76,230 CIK prefixes (200,349 `main`, 3,996 `pagination`). The newest `main` object per
  CIK was taken for 4,831 owner CIKs + 1,877 issuer CIKs (6,696 files, 268 MB).
- `filings/sec/cik=<cik>/accession=<acc>/primary/*.xml` -- the **legacy** fetch path's bronze
  (`warehouse_paths.properties:21`, research 11 F3): 510,649 objects, 141,000 under `primary/`, 114,595
  of them `.xml`. Used only for the representativeness check and the entity-arm supplement (F8).

Repo code:
- `edgar_warehouse/parsers/ownership.py:17` (`Ownership.from_xml`), `:24-39` (owner row fields; flags
  at `:31-34`, `officer_title` `:35`); the parser keeps neither `otherText`, footnotes, remarks nor
  signatures.
- `edgar_warehouse/mdm/pipeline.py:1457-1459` (legacy's only classification: drop `owner_cik` in the
  company-CIK set), `edgar_warehouse/mdm/sql_fragments.py:57-63` (`INDIVIDUAL_ONLY_OWNERSHIP_FORMS`).
- `pyproject.toml:16` (`edgartools>=5.29.0`), `uv.lock:655-656` (resolved `5.30.0`).

edgartools (PyPI), read at the installed source, two versions:
- 5.58.0 (what `uv run --with edgartools` resolves today): `edgar/ownership/owners.py:103-160`
  (`ReportingOwners.from_reporting_owner_tags`), `:117` (`is_company = entity and entity.data.is_company`),
  `:126-130` (the four flags read from `reportingOwnerRelationship`); `edgar/entity/core.py:274`
  (`get_entity_submissions(self.cik)`), `edgar/entity/submissions.py:132,162`
  (`download_entity_submissions_from_sec`); `edgar/entity/data.py:481-514` (`is_individual`, first 50
  forms), `edgar/entity/constants.py:12` (`COMPANY_FORMS`, 100 entries, includes `PX14A6G`), `:163`
  (`COMPANY_NAME_KEYWORDS`), `:182` (`COMPANY_NAME_KEYWORDS_STRICT`), `:212`
  (`COMPANY_NAME_TERMINAL_SUFFIXES`), `:240` (`_name_suggests_company`), `:282-346`
  (`_classify_is_individual`, signals 1-9 at `:304,308,313,318,323,329,335,340,345`).
- 5.30.0 (the lockfile): same network call at `edgar/ownership/ownershipforms.py:1017-1020`; the
  `_classify_is_individual` body is byte-identical (SHA-256 prefix `96c2185093e2` in both), at
  `edgar/entity/constants.py:226`; `COMPANY_FORMS` is the same 100 entries; the keyword sets differ
  slightly (30/14 entries vs 29/17 plus the terminal-suffix set that 5.30.0 lacks).

Sibling files (same directory):
- `18-classify.py` -- `parse` / `sample` / `score` / `extend` / `score-extension`; sockets are blocked
  at import.
- `18-owners.jsonl` -- 5,743 owner rows (one per `<reportingOwner>`), each with the flags,
  `officer_title`, `otherText`, deputization/self-description snippets, signature names, SGML-header
  fields, name tokens, and the joined `submissions.json` fields.
- `18-sample.jsonl` -- the 1,220 labeled owners (draft label, my label, reason, `uncertain`).
- `18-sample-plan.json` -- population and sample size per stratum.
- `18-summary.json` -- every count and the scored table; `18-extension-*.json[l]` -- the F8
  supplement.

## Method

**Unit.** Rows (5,743) are what a rule classifies; labels were made once per **distinct owner CIK**
(4,831) on its first accession in sort order, because the same person on 20 filings is not 20
observations. Precision is reported on owners (unweighted, with Wilson 95% intervals on the raw
counts) and, for reference, population-reweighted by stratum (`*_weighted` in the JSON). Deferral
share is reported on all 5,743 rows and on all 4,831 owners by applying each rule to the whole
population, so it carries no sampling error for this corpus.

**Strata.** Flag combination x entity-token presence, 23 non-empty cells (`18-sample-plan.json`).
The three big person-looking cells were sampled at 200 each; `10pct|token` (268) and every cell of
<= 60 owners were taken in full; the rest capped at 60. Seed `20260920`. Counts per cell are in F5.

**Labeling rule** (`draft_label` in the script, then my pass over every one of the 1,220 lines):
name reading is primary (EDGAR's conformed `LAST FIRST MIDDLE` form vs a legal-form token);
`submissions.json` evidence is used only where it is *strong* (tickers/exchanges, issuer forms such
as 10-K/8-K/S-1/N-CEN, 13F-HR or ADV, an EIN) and any conflict with the name was left for me to
decide. `entityType`, the four flags and the ticket-03 token list were deliberately **not** decisive
in the draft, because they are the candidate rules. I overrode 16 drafts (all named in
`18-summary.json.draft_overrides`) and marked 4 owners uncertain (F6).

**The 99% bar.** With a perfect observed record the Wilson lower bound is `n/(n+z^2)` = `n/(n+3.8416)`,
so **n >= 381 error-free decisions** are needed for a 0.99 lower bound; one error needs about 600.
This is per decision bucket (person, entity), not per sample.

## Findings

### F1 -- The population, and what the numbers describe

5,356 filings -> 5,743 owner rows -> 4,831 distinct owner CIKs. Forms: 4 = 5,157, 3 = 488, 4/A = 87,
3/A = 10, 5 = 1. Every row has an `rptOwnerCik` (0 missing) and **every one of the 4,831 owner CIKs
has a bronze `submissions.json`** -- zero SEC fetches were needed; the only two CIKs without a
payload are issuer CIKs, not owners. 506 rows (8.8%) sit on the 119 multi-owner filings (2.2% of
filings), the case where every transaction is hard-attached to owner 1 (research 11 F5).

This is the **gated-capture** corpus (`filing_artifact/`, written since the Ticket 27 cutover), so it
is recent: `periodOfReport` runs 2025-2026 and it is a partial slice of the tracked universe. The
legacy prefix holds 114,595 primary `.xml` objects, ~83% of them `<ownershipDocument>` -- roughly 20x
this corpus; F8 checks the flag/token distribution against it.

### F2 -- Flag-combination distribution (all 5,743 rows)

| combination | rows | share | distinct owners | token-bearing rows | entityType op/inv rows |
|---|---|---|---|---|---|
| officer only | 2,320 | 40.4% | 2,062 | 2 | 2 |
| director only | 1,818 | 31.7% | 1,604 | 32 | 2 |
| officer+director | 616 | 10.7% | 524 | 0 | 0 |
| **10% only** | 526 | 9.2% | 339 | 422 | 22 |
| other only | 147 | 2.6% | 72 | 17 | 4 |
| officer+director+10% | 145 | 2.5% | 105 | 2 | 0 |
| director+10% | 112 | 2.0% | 77 | 46 | 2 |
| 10%+other | 21 | 0.4% | 16 | 14 | 1 |
| director+other | 13 | 0.2% | 12 | 0 | 0 |
| officer+10% | 10 | 0.2% | 6 | 0 | 0 |
| five rarer mixes | 15 | 0.3% | 14 | 2 | 0 |
| none | 0 | | | | |

The 10%-only cell is the mixed one ticket 03 must rule on: 422 of its 526 rows carry an entity
token, but of its 66 no-token owners I labeled 60 and found **50 natural persons and 10 entities**
(large individual holders -- Adelson, Gates, Kravis, Schwarzman, Malone -- next to labor-union locals
with no legal-form token). "10%-only => not a person" is wrong for roughly one owner in six of that
cell; scored as R2 it reaches only 72.3% entity precision.

### F3 -- `entityType` coverage, and why it cannot carry the decision

Owners by `entityType`: `other` 4,809 (99.5%), `operating` 20, `investment` 2; no owner lacks a
payload. Among the 4,809 `other` owners, 362 have at least one structural field populated (`sic` 15,
`stateOfIncorporation` 347, `ein` 62, tickers 3, `ownerOrg` 15, `fiscalYearEnd` 336) and 4,447 have
none. So `operating`/`investment` is a precise but tiny entity signal (22 owners, 100% in the
sample, LCB 0.85), and `other` is where every fund, LLC, trust and union sits alongside the persons:
ticket 03's R1 ("`other` = individual") scores **71.0%** person precision.

The structural-emptiness rule (R4) is much better but has a hard floor: **SEC populates
`stateOfIncorporation`/`fiscalYearEnd`/`sic`/`ownerOrg` on a minority of genuine person CIKs** --
among the 4,461 person-shaped, token-free owners, 31 carry `stateOfIncorporation`, 29 `fiscalYearEnd`,
9 `sic`, 9 `ownerOrg`, 2 `ein` (~0.7%; e.g. `MALONE JOHN C` soi=CO/fye=1231, `AULT MILTON C III`
soi=DE, `HOUGEN ELIZABETH L` sic=2835/soi=DE/ownerOrg="03 Life Sciences"). Any rule that reads a
populated structural field as "entity" misclassifies these persons, and 8 of them landed in the
sample: that is the whole gap between 97.6% and 100% on the entity arm of R4/C-A..C-G/R6.

### F4 -- Deputization and `otherText`

`otherText` is non-empty on 196 rows (3.4%); the top values are role labels (`Portfolio Manager` 45,
`Senior Vice President/Inv. Mgr` 18, `VP` 17, `Member of 10% owner group` 14, `See Remarks`/`See
Explanation of Responses` 21) and **`Director-by-Deputization` on 4 rows**. Searching
`otherText`+`officerTitle`+footnotes+remarks for `deputi[sz]` hits **50 rows (0.87%) on 15 filings,
34 distinct owners**; the broad pattern (designee/board representative) adds 6 rows. By flag
combination: director-only 21, director+10% 20, director+10%+other 4, 10%+other 3,
officer+director+10% 2. 29 of the 34 owners are entities (Silver Lake, Invesco, Basswood, Fairmount,
Sumitomo Mitsui, Diamondback Energy, Bpifrance, PWP VoteCo); 5 are natural persons who co-file on the
same document (the Lindenbaums, Ault, Durban, Harwin, Kiselak) -- the text refers to the entity, not
to them. So the hazard ticket 03 named is real but small (1 director-flagged row in ~100), and the
raw XML is the only place it is visible: the repo parser drops all four text fields
(`parsers/ownership.py:24-39`).

### F5 -- The labeled truth set

1,220 owners: 851 person, 369 entity. Per stratum (population owners / sampled / person / entity):

| stratum | pop | n | person | entity |
|---|---|---|---|---|
| officer\|notoken | 2,061 | 200 | 200 | 0 |
| director\|notoken | 1,575 | 200 | 200 | 0 |
| officer+director\|notoken | 526 | 200 | 200 | 0 |
| 10pct\|token | 268 | 271* | 0 | 271 |
| officer+director+10pct\|notoken | 106 | 60 | 60 | 0 |
| 10pct\|notoken | 66 | 60 | 50 | 10 |
| other\|notoken | 58 | 59* | 59 | 0 |
| director+10pct\|notoken | 43 | 45* | 45 | 0 |
| director+10pct\|token | 35 | 32* | 0 | 32 |
| director\|token | 29 | 29 | 0 | 29 |
| other\|token | 13 | 13 | 1 (`Trust Jane`) | 12 |
| director+other\|notoken | 12 | 12 | 12 | 0 |
| 10pct+other\|token | 10 | 10 | 0 | 10 |
| 10pct+other\|notoken | 6 | 6 | 6 | 0 |
| officer+10pct\|notoken | 6 | 6 | 6 | 0 |
| officer+director+other\|notoken | 4 | 4 | 4 | 0 |
| six cells of <= 3 | 12 | 12 | 8 | 4 |

\* the sample was drawn on a representative row per owner, so a cell's sample can differ by a few
from its population count when an owner's flags differ across filings (the population count uses
the first accession; `flag_combos_seen` in the JSONL lists all).

Labels rested on the name alone for 1,056 owners and on name plus a strong structural field for 164
(all entities). Two entity-side facts worth naming: three entities carry the **officer** flag with a
title (`JI XIANG HU TONG HOLDINGS LTD` and `SHAN LAO HU TONG LLC`, "Chief Executive Officer";
`CTT PHARMACEUTICAL HOLDINGS, INC.`, "CEO"), and eight union bodies ("Workers United" joint boards)
carry no legal-form token at all.

### F6 -- Uncertain cases (all four, verbatim from `18-sample.jsonl`)

- `FDB I` (CIK 2094716, 10%-only, no token) -> **entity**: unreadable name; soi=E9 (Cayman) and FYE
  populated point to a fund vehicle.
- `FROST PHILLIP MD ET AL` (898860, 10%-only) -> **person**: Dr. Phillip Frost's own CIK with an "et al"
  group designation.
- `Jonathan Scott as Trustee of the Jonathan R Scott Trust Dated as of 4/21/04` (1908962) -> **entity**:
  a CIK registered in trustee capacity; treated as the trust, not the man.
- `Trust Jane` (1640286, other-only, token `TRUST`) -> **person**: officer title "Dir Pres CEO, Pres&
  CEO/InvMgr", POA signature "for Jane Trust", no structural field. The only name-token failure.

The 16 draft overrides (union boards, a German UG, `BANK OF AMERICA NA`, `Parallel49 Equity, ULC`,
`Aljomaih Automotive Co.`, `GOLDSTEIN PHILLIP`, `Bulho Matheus De A G Viera`, `Trust Jane`, plus the
eight persons with populated structural fields) are listed with reasons in
`18-summary.json.draft_overrides` and carry `label_reason` in the JSONL.

### F7 -- Scored rules

Person arm = owners the rule auto-labels `person`; entity arm = auto `entity`; deferral = share of
the whole population the rule sends to a Steward. `n` and precision are unweighted sample counts;
Wilson 95% lower bound in brackets. **Bold** clears 0.99 at the lower bound.

| rule | person n | person prec [LCB] | entity n | entity prec [LCB] | defer rows | defer owners |
|---|---|---|---|---|---|---|
| R1 `entityType` (ticket 03 item 1: op/inv -> entity, `other` -> person) | 1,198 | 0.7104 [0.684] | 22 | 1.0000 [0.851] | 0.0% | 0.0% |
| R1b `entityType`, `other` deferred | 0 | -- | 22 | 1.0000 [0.851] | 99.4% | 99.5% |
| R2 flags (off/dir -> person; 10%/other -> entity) | 801 | 0.9176 [0.897] | 419 | 0.7232 [0.678] | 0.0% | 0.0% |
| R2b flags (off/dir -> person; rest deferred) | 801 | 0.9176 [0.897] | 0 | -- | 12.1% | 8.8% |
| R3 name tokens (token -> entity; person-shape -> person) | 853 | 0.9953 [0.988] | 360 | 0.9972 [0.984] | 0.3% | 0.2% |
| R3b R3, ambiguous tokens deferred | 853 | 0.9953 [0.988] | 357 | 0.9972 [0.984] | 0.3% | 0.3% |
| R4 structural-empty (`other` & no sic/soi/ein/ticker/org/fye -> person; else entity) | 860 | 0.9802 [0.969] | 360 | 0.9778 [0.957] | 0.0% | 0.0% |
| R4b R4, token-bearing persons deferred | 842 | **1.0000 [0.9955]** | 360 | 0.9778 [0.957] | 0.4% | 0.4% |
| R5 form history (only 3/4/5 -> person; issuer/institutional forms -> entity) | 520 | 0.7231 [0.683] | 152 | 0.9737 [0.934] | 47.6% | 48.2% |
| C-A off/dir & no token & structural-empty -> person; structural or token -> entity | 727 | **1.0000 [0.9947]** | 377 | 0.9761 [0.955] | 3.8% | 2.5% |
| C-B C-A without the flag requirement | 841 | **1.0000 [0.9955]** | 377 | 0.9761 [0.955] | 0.07% | 0.08% |
| C-C C-B + deputization text -> deferred | 841 | **1.0000 [0.9955]** | 377 | 0.9761 [0.955] | 0.2% | 0.2% |
| C-D C-B + form-history guard | 834 | **1.0000 [0.9954]** | 378 | 0.9762 [0.955] | 0.3% | 0.3% |
| C-E C-D, person only for off/dir rows | 722 | **1.0000 [0.9947]** | 378 | 0.9762 [0.955] | 4.0% | 2.7% |
| R6 edgartools `_classify_is_individual` (offline on bronze) | 841 | **1.0000 [0.9955]** | 379 | 0.9736 [0.952] | 0.0% | 0.0% |
| C-F R6 person only when name/structural/deputization checks agree | 840 | **1.0000 [0.9954]** | 379 | 0.9736 [0.952] | 0.3% | 0.2% |
| C-G C-F, person only for off/dir rows | 726 | **1.0000 [0.9947]** | 379 | 0.9736 [0.952] | 4.0% | 2.7% |
| C-H person: no token & structural-empty & person-shape; entity: op/inv `entityType` OR unambiguous token | 841 | **1.0000 [0.9955]** | 357 | 0.9972 [0.984] | 1.1% | 1.0% |
| C-I C-H + two-word surname-token names deferred (post-hoc, F6) | 841 | **1.0000 [0.9955]** | 356 | 1.0000 [0.9893] | 1.1% | 1.0% |
| **C-J** C-H + single-token, person-shaped, structural-empty names deferred (post-hoc, F8) | 841 | **1.0000 [0.9955]** | 353 | 1.0000 [0.9892] | 1.2% | 1.1% |

Reading the table:

- **The person arm clears 99% on every rule that requires all three of: no entity token,
  structural-empty `submissions.json`, person-shaped name** (R4b, C-B..C-J, R6, C-F): 841/841, LCB
  0.9955. Adding the officer/director flag requirement (C-A, C-E, C-G) buys nothing in precision and
  costs 2.5-2.7% of owners deferred (the 10%-only and other-only persons). The flags-only rule R2 is
  91.8% because 10%-only/other-only persons are common; the token-only rule R3 is 99.5% because eight
  union bodies and `FDB I` carry no token. Population-reweighted, the same rules are 1.0000.
- **The entity arm is population-limited.** This bronze holds 360 token-bearing owners and I labeled
  all of them, so R3/C-H/C-I's entity arm is a *census* of this corpus (359/360, 356/357, 356/356),
  not a sample of it; the Wilson interval speaks to generalization to future filings, and there the
  arithmetic is fixed: 356 error-free decisions give LCB 0.9893, 381 are needed. No rule clears 0.99
  on the entity arm from the primary corpus alone; F8's legacy-corpus supplement is what lifts C-J
  past the bar, under its post-hoc guard. The structural family (R4, C-A..C-G, R6) is worse in
  kind, not just in n: 97.4-97.8% with the eight populated-field persons as the errors.
- **C-H is the best rule with no post-hoc guard**: person 841/841, entity 356/357 (`Trust Jane`), 64
  rows (1.1%) / 48 owners (1.0%) deferred. C-I and C-J add a surname-token guard written *after* the
  error cases were seen (C-I after `Trust Jane`; C-J after the extension in F8 produced
  `Council LaVerne H`, which C-I's two-word test misses). Their entity arms should be read as "no
  error observed", not as tested improvements over C-H.
- **edgartools' own chain (R6)** matches the best person arm exactly (841/841) and adds one entity-arm
  error the others do not have: `Kravetz Shawn W` (forms `PX14A6G, SC 13D`) is called a company
  because `PX14A6G` -- an exempt-solicitation notice individual activists file -- is in
  `COMPANY_FORMS` (`edgar/entity/constants.py:12`), so signal 5 (`:323-328`) fires before the name is
  consulted. Signal 3 (`stateOfIncorporation` => company, `:313-317`, with a hard-coded exception for
  one CIK) is the same structural floor as F3.

### F8 -- Representativeness check and entity-arm supplement from the legacy corpus

All 114,595 primary `.xml` objects under `filings/sec/` were downloaded (112,490 distinct
accessions; a few accessions carry two primaries): 91,110 are `<ownershipDocument>`, 21,380 are
other XML (13F/ADV `edgarSubmission` etc.), 0 failed to parse. They yield **101,137 owner rows,
19,735 distinct owners** (2,839 of them also in the primary corpus); forms 4 = 91,475, 3 = 7,725,
4/A = 1,341, 5 = 341, 3/A = 250, 5/A = 5; 0 rows without `rptOwnerCik`
(`18-extension-stats.json`).

**Distribution check.** Row shares by flag combination, legacy vs primary: officer-only 39.0% vs
40.4%; director-only 32.8% vs 31.7%; officer+director 10.1% vs 10.7%; 10%-only 9.8% vs 9.2%;
director+10% 3.5% vs 2.0%; officer+director+10% 2.6% vs 2.5%; other-only 1.1% vs 2.6%. Token share
inside 10%-only: 82.8% vs 80.2%. Multi-owner rows 12.6% vs 8.8%; strict deputization 3.1% of rows
vs 0.9% (the Silver Lake / Invesco / Warburg Pincus groups file far more often over a 2-year window
than in the recent slice). The primary corpus is therefore representative on the axes the rules
read, and under-represents the joint-filing entity groups where deputization lives.

**Entity-arm supplement.** The legacy corpus has 2,037 token-bearing owners, 1,755 of them absent
from the primary corpus, 1,044 of those with a bronze `submissions.json` (the other 711 would have
needed SEC fetches and were not sampled). 160 were drawn deterministically (seed `20260920`) and
labeled the same way (`18-extension-sample.jsonl`): **159 entity, 1 person** -- `Council LaVerne H`
(CIK 1788616, director, POA signature "for LaVerne H. Council", no structural field), a second
person whose surname is a legal-form token, three words long. Three were unsure and resolved as
entities (`ALLIANZ SE`, `UAW Ford Retirees Medical Benefits Plan`, `GPI SA`). The person arm was
**not** re-drawn over the union (owners that appear only in the legacy prefix had zero inclusion
probability in the 1,220-owner sample), so this supplement scores the entity decision only.

Entity arm, extension alone and pooled with the primary sample (`18-extension-summary.json`):

| rule | extension entity n | correct | pooled n | pooled prec | pooled LCB |
|---|---|---|---|---|---|
| R3 name tokens | 160 | 159 | 520 | 0.9962 | 0.9861 |
| R4 structural-empty | 154 | 154 | 514 | 0.9844 | 0.9696 |
| C-B..C-E (structural family) | 160 | 159 | 537-538 | 0.9814 | 0.9661 |
| R6 edgartools | 158 | 158 | 537 | 0.9814 | 0.9661 |
| C-H | 157 | 156 | 514 | 0.9961 | 0.9859 |
| C-I (two-word guard) | 157 | 156 | 513 | 0.9981 | 0.9890 |
| **C-J** (single-token guard) | 154 | 154 | 507 | 1.0000 | **0.9925** |

Two more facts from the supplement: R6 (edgartools) auto-labels `UAW Ford Retirees Medical Benefits
Plan` a **person** -- its chain has no `PLAN` keyword and ignores `fiscalYearEnd`, the only populated
field -- so its person arm is not error-free outside the primary corpus; and every structural-family
rule again pays for a populated-field person or a field-less entity, not for a token.

**What C-J defers** (52 of 4,831 owners in the primary corpus, listed by running `rule_combo_j` over
`18-owners.jsonl`): 37 person-shaped names with a populated structural field (the Malone/Ault/Lindner
class, plus every "Workers United" board, `FDB I`, `Refo SCSp`, the German UG), 3 multi-part
Portuguese names outside the 2-5-word shape, 3 ambiguous-token names (`BANK OF AMERICA NA`,
`Parallel49 Equity, ULC`, `Aljomaih Automotive Co.`), and 4 single-token names caught by the guard
(`Trust Jane`, `SLJ Dynasty Trust`, `IVZ Inc`, `PERIDOT COINVEST MANAGER LLC`). In the extension it
defers 6 of 160 (`Council LaVerne H` plus five entities). So the guard's cost is roughly 1-3% of
entities sent to a Steward, and its benefit is the two surname-token persons. For the Steward-queue
volume ticket 03 cares about: C-J's deferred set is ~1% of owners and is dominated by *persons* (37
of the 52 are the structural-populated person class), so the queue is mostly people SEC tagged with
a state/FYE, not ambiguous entities.

### F9 -- What the repo parser does that this measurement had to avoid

`parse_ownership` calls `Ownership.from_xml` (`parsers/ownership.py:17`). In both the locked
5.30.0 (`edgar/ownership/ownershipforms.py:1017-1020`) and current 5.58.0
(`edgar/ownership/owners.py:117`) that constructor runs `Entity(int(cik)).data.is_company` for
**every reporting owner**, which downloads `https://data.sec.gov/submissions/CIK<cik>.json`
(`edgar/entity/submissions.py:132`) at parse time -- confirmed here by blocking sockets: `from_xml`
raised from `httpcore` on the first owner, and with sockets open the 5,356-file parse ran >10 minutes
of mostly network wait before being killed. The repo's warehouse parse therefore already makes one
SEC request per reporting owner (unless edgartools' local cache has it) and already computes an
`is_company` that `parse_ownership` discards. Two consequences for ticket 03: (i) the classifier is
there to be reused, but it should be fed the **bronze** `submissions.json`, not a live fetch; (ii)
its result must not be taken as the person rule wholesale, because of the `PX14A6G` and
`stateOfIncorporation` behaviors in F7.

## What this settles for ticket 03

1. **Automatic `person` at >= 99% precision is achievable with near-zero deferral**: rule "no
   legal-form token in the name AND `submissions.json` structurally empty (no sic, stateOfIncorporation,
   ein, tickers, ownerOrg, fiscalYearEnd) AND person-shaped name" -- 841/841 in the sample, Wilson LCB
   0.9955, and it does not need the relationship flags at all (requiring officer/director only defers
   the 10%-only persons, ~2.6% of owners, for no precision gain).
2. **Automatic `company`/entity: the name-token rule measures 99.6% (518/520 pooled, LCB 0.986) and
   does not clear 99% at the lower bound.** Both errors are natural persons whose surname is a
   legal-form token (`Trust Jane`, `Council LaVerne H`). The primary corpus alone holds only 360
   token-bearing owners (n >= 381 needed even error-free), which is why the legacy supplement was
   added. With a guard that defers single-token, person-shaped, structurally-empty names (C-J) the
   pooled entity arm is 507/507, LCB 0.9925 -- **that does clear 99%, but the guard was written after
   both errors were seen**, so the number is "no error observed under the guard", and its own miss
   rate (a surname-token person with a 6-word name, or two tokens) is unmeasured.
   `entityType in (operating, investment)` is 100% but covers 31 owners. Any rule that reads a
   populated `stateOfIncorporation`/`fiscalYearEnd` as "entity" tops out at 97.6-98.1% because SEC sets
   those on ~0.7% of person CIKs; that family cannot reach 99% on the entity arm.
3. **Deferral cost: C-H 1.1% of rows / 1.0% of owners; C-J 1.2% / 1.1%** -- the token-free entities
   (union locals, `FDB I`), the ~0.7% structural-populated persons, ambiguous tokens, and (C-J) the
   single-token names. The 10%-only cell must not be coerced: 50 of its 60 labeled no-token owners are
   natural persons.
4. **Deputization is a 0.9%-of-rows footnote phenomenon, not a flag**: it lives in `otherText`/footnotes
   the parser drops, and 29 of the 34 owners it touches are already entities by name. Deferring on the
   text (C-C) changes nothing in precision and costs 0.2%.
5. **The never-fetched case did not occur**: 4,831/4,831 owner CIKs had a bronze payload. Ticket 03
   still needs a rule for it (defer), but it has no measured frequency here.

## Could not be determined

- Whether the person arm's 100% holds on the legacy-era corpus: the person arm was drawn from the
  gated-capture corpus only (owners appearing only in the legacy prefix had zero inclusion
  probability) and was deliberately not re-drawn over the union.
- The true miss rate of the surname-token guards (C-I, C-J): two triggering persons exist across
  both corpora, and both guards were written after seeing them.
- The 711 legacy token-bearing owners with no bronze `submissions.json` (F8): not sampled, so
  whether "never fetched" correlates with entity kind is unknown.
- Whether the 8 structural-populated person CIKs are an SEC data-entry artifact or reflect a filer
  agent registering the person with an issuer's profile: `HOUGEN ELIZABETH L` carries an issuer's
  SIC/office, the others only a state and FYE; nothing in the payload says why.
- Why edgartools' `from_reporting_owner_tags` fetches submissions at parse time rather than accepting
  an injected payload; no option was found in either version.
- The frequency of multi-owner filings in the legacy corpus by *distinct* owner, since the legacy
  supplement labeled token-bearing owners only.
