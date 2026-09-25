# Prove and switch on the SEC Company classification rule

Type: task
Status: proof complete; activation pending operator approval
Blocked by: ticket 06 exact-digest approval for activation

## Question

Shell and ASML wait in the Stage because the standard SEC Company rule is
declared but inactive. SEC calls a foreign issuer `other`, as it does an
individual; the issuer also carries an industry code and filer category. The
candidate rule `sec-company-candidate` distinguishes them, but a rule acts
alone only on a measured proof (§9.2) and the operator's approval of one exact
digest.

This is the **classification** part of ticket 05's Proving Run, carved out:
ticket 05 as written measures SEC-to-GLEIF matching and waits on ticket 08.
Ticket 06's approval remains pending and is not asked or recorded here.

## Decisions (operator, 2026-09-24)

- **An SEC `investment` filer is a Fund, not a Company.** Bronze: all 1,793
  file fund forms (N-CEN, 485BPOS, N-CSR, NPORT-P); they are mutual funds,
  trusts and insurance separate accounts. Step 1 drops `investment`; they wait
  in the Stage until the Fund kind exists (about 19:45 ET).
- **A business development company (BDC) is a Company.** SEC types it
  `operating`; 193 of the 200 `operating` filers with no industry code are
  BDCs (10-K, 10-Q, 8-K plus N-54A). It is a legal company with its own
  shares; the Fund kind may later add a Fund profile to it (about 19:50 ET).
- **An asset-backed loan trust is not a Company** (1,040; SIC 6189); they
  wait (about 20:00 ET).
- **An exchange-traded commodity or crypto trust, or a futures pool, is a
  Fund** (about 150; SIC 6221); they wait (about 20:10 ET).
- **A private fund that registers with SEC by Form 10 and is not a BDC is a
  Fund**, including holding-company-style vehicles (KKR Private Equity
  Conglomerate, EQT Private Equity Co); it waits (2026-09-25 05:58 ET).
- **A private REIT that registers with SEC by Form 10 and raises money
  privately (Form D) is a Fund** (Goldman Sachs Real Estate Finance Trust,
  Sculptor Diversified Real Estate Income Trust, HPS Net Lease Income REIT);
  listed and publicly offered REITs stay Companies (2026-09-25 06:09 ET).
- **"Fund" in these rulings means a Fund Structure identity** (with a Fund
  profile), not a Company holding a Fund profile, even where the arrangement
  is a legal person (a Delaware LP fund). BDCs stay Companies with a Fund
  profile. *Recommended, not yet decided:* Fund Structure, Person,
  Government Entity and International Organization records wait in the Stage,
  labelled with the kind that will own them, until the Company gate passes,
  and Person comes first after it (2026-09-25 06:32 ET).
- The Company classification bar is **95%** at 95% one-sided confidence
  (confidence bands, `company-policy.md`); merging two published Company IDs
  keeps 99.9%.

## Checklist

Kept current per the task-checklist rule (CLAUDE.md). Times are local ET.

- [x] Accepted bars per (kind, family): Company classification 0.95; a family
  with no accepted bar (Company consolidation today) cannot declare one — unit
  (2026-09-24 19:58 ET)
- [x] Historical freeze, superseded by 2026-09-24.7: version 2026-09-24.6 (industry codes 6189, 6221, 8888
  wait; `operating` is a Company; `other` needs an industry code and a
  legal-form word, and a person's suffix waits) (2026-09-24 20:18 ET)
- [x] Historical .6 draw, superseded by the per-step .7 draw: label a simple random sample of the rule's `company` verdicts from
  evidence the rule does not read; adversarial fixture of individuals, funds
  and every individual with an industry code; script, sample and SHA-256s
  committed — `research/12-*` (2026-09-24 20:22 ET)
- [x] Historical .6 score, superseded by the per-step .7 score: Wilson lower bound: 297 of 300, **0.97524**; step 2 0.97395, step 4
  0.93931; adversarial 294, 0 violations (2026-09-24 20:22 ET)
- [ ] ~~Operator approves the exact policy digest (ticket 06):
  `b26ab87c208e1efc5507c583e426c28472c7d07bef0871c093e13985cc6112d1`
  (2026-09-24 21:05 ET). A first "yes" at 20:27 ET was withdrawn: the
  question named the digest without saying what one is. The body's
  `approved_at` (00:26:27Z, 20:26 ET) is when it was prepared; changing it
  would change the digest approved, so the true time is kept here.~~ Withdrawn
  after the per-step review; new approval pending a qualifying proof.
- [x] Draw and hand-label 300 records separately for each Company step under
  rule 2026-09-24.7; record notes for every fund-, trust-, and
  partnership-looking name — frozen JSONL and review script, SHA-256 check
  (2026-09-24 21:28 ET).
- [x] Hand-label the name-blind adversarial fixture and score each step's
  one-sided 95% lower bound and all non-Company violations — 297/300 and
  0.97524 for step 2; 258/300 and 0.82382 for step 4; 33 violations of 483
  adversarial records, independently scored from frozen JSONL
  (2026-09-24 21:28 ET).
- [x] Pin the new proof and source-file hashes in the local Company source;
  leave the rule inactive without new operator approval — `PROOF` hash test,
  empty `POLICY.automatic_rules`, absent `approved_at` verified
  (2026-09-24 21:29 ET).
- [x] Repair classification, source, activation, and integration tests; add
  a check that re-hashes the research files against the proof — 97 focused
  MDM tests passed; PG16 tests collected but sandbox denied Colima socket
  (2026-09-24 21:29 ET).
- [x] Write a plain-English approval brief with the exact digest, per-step
  numbers, and reversal; keep approval pending — `12-approval-brief.md`
  reviewed against `PROOF` and policy digest (2026-09-24 21:29 ET).
- [x] Run MDM and architecture tests and attempt local PG16 integration —
  888 MDM and 570 architecture tests passed; PG16 setup blocked by Colima
  socket permission, not a test assertion (2026-09-24 21:29 ET).
- [x] Commit the proved failed gate and pending approval brief on the Codex
  branch as `476003cd` (`git diff --cached --check`, 2026-09-24 21:32 ET).
- [x] Version .8 requires SEC filer category for step 4; verified
  `stage_company_loader` supplies it and `adapters.normalize` passes the row
  to `fired`; missing-category unit test passes (2026-09-24 21:43 ET).
- [x] Draw and hand-read seed-20260924.8 samples of 300 per Company step;
  draft labels use forms, tickers and exchanges, with notes on every
  fund-, trust- and partnership-looking name; frozen JSONL and scorer checks
  verify the draw (2026-09-24 21:43 ET).
- [x] Score steps independently: step 2 299/300 (0.98520), step 4 300/300
  (0.99106); adversarial 0 violations in 483. Codex scored 300/300 at step 2;
  Claude's recheck of every fund-like name (21:50 ET) counts Stonepeak-Plus
  Infrastructure Fund LP as a Fund. Stage the activation proposal,
  with approval fields unset and `automatic_rules` empty (2026-09-24 21:43 ET).
- [x] Rewrite the operator brief, pin pending policy digest and all five proof
  file hashes; re-hash verification passes, approval pending
  (2026-09-24 21:44 ET).
- [x] Run MDM and architecture tests and retry PostgreSQL 16 with Colima
  (2026-09-24 22:07 ET: MDM 889, architecture 570, PG16 130 passed; two PG16
  tests fixed for the policy the SEC contract now needs; 1 `fastapi` baseline;
  CI green on 72b76362).
- [x] Codex stopped at the operator's word (21:47 ET) before committing its
  second pass; the operator handed the work back to Claude (21:48 ET), which
  took it onto `claude/company-mastering-12-prove-sec-classification`.
- [ ] ~~Register an activated rule in the standard policy and verify it on
  four Companies~~ deferred to ticket 06: exact-digest operator approval and
  true `approved_at` are pending. `PENDING_ACTIVATION` records the measured
  proposal; the standard policy remains inactive.
- [x] Three-axis `/code-review` of 72b76362 (2026-09-24, finished before 22:21 ET). GoF: leave
  it (also taken as the pre-code consult on `activation.py` for the next
  item). Standards: no hard violations. Spec: four findings, below.
- [x] Spec finding: `_check_proof` judged only the pooled sample. It now needs
  a sample of its own for every step that emits the verdict, each clearing
  the bar; tests for a failing step and a missing step (2026-09-24 22:21 ET).
- [x] Spec finding: the first adversarial fixture was fixed before `.8` and
  `.8` removed exactly its 33 violations, so its 0 is in-sample. Drew a fresh
  arm after `.8` (`12-adversarial-2.py`, seed `20260924.8-adversarial-2`),
  chosen by evidence the deciding step does not read, 339 records, every one
  hand-read (2026-09-24 22:21 ET).
- [ ] **Step 2 fails the fresh arm: 18 of 200 are Funds; step 4: 0 of 139.**
  Seven rest on decisions already made (3 exchange-traded crypto trusts, 4
  registered investment companies); eleven are private vehicles registered by
  Form 10 with no BDC election, on which the operator has not ruled. The
  current proof's "0 adversarial violations" is superseded. **No approval is
  asked; PR 710 must not merge** (merging it makes Apple and Microsoft wait
  too, because the SEC contract now names the rule and the rule is off).
- [x] Operator (2026-09-25 05:58 ET): a private fund that registers with SEC by Form 10 and
  is not a BDC is a **Fund**, including holding-company-style vehicles such as
  KKR Private Equity Conglomerate.
- [x] Version `2026-09-25.9` (recorded at the commit time below): three hold-back steps before `operating`
  becomes Company: a fund word in the name (2), a finance-office code with
  filer category exactly `<br>Emerging growth company` (3), no industry code
  (4). Holds back 419 of 5,980 `operating` filers (7.0%), mostly BDCs and new
  crypto-treasury companies; Apple and Microsoft unaffected (2026-09-25 06:04 ET).
- [x] Fresh draws after the freeze (seed `20260925.9`, `12-measure-9.py`),
  all 1,032 records hand-read (`12-9-label.py`) (2026-09-25 06:04 ET):
  step 5 **298/300** (lower bound 0.9801), step 7 **300/300** (0.9911); both
  clear 0.95. Wrong: GPB Holdings II (Form-10 private vehicle, SIC 8742) and
  Goldman Sachs Real Estate Finance Trust (private REIT, pending).
- [ ] **Adversarial: 3 of 432 violations** (step 5: Sculptor Diversified Real
  Estate Income Trust, HPS Real Assets Lending Co LP; step 7: HPS Net Lease
  Income REIT). If private Form-10 REITs are Companies, 1 (HPS Real Assets
  Lending). Either way the zero-violation proof fails at step 5: Form-10
  private vehicles also sit under ordinary industry codes (6500, 8742), and
  the rule cannot see the forms a filer files.
- [x] Operator (2026-09-25 06:09 ET): private REITs that register by Form 10 are **Funds**.
  Noted for the operator as read as Companies: listed royalty trusts (North
  European Oil Royalty Trust, MV Oil Trust), CNL Strategic Capital.
- [ ] Defect found (2026-09-25): `token_match@1` counts an ampersand for every
  word list, although the design (`policy-language.md`; the Person list
  carries `AND`) counts it only for a list that carries `AND`. No Company
  list does. Effect: step 2 holds back about 157 companies with `&` in the
  name (McCormick & Co, Marsh & McLennan), and step 6 holds back every
  `other` name with `&` before step 7. No wrong Company call results; fixing
  it changes steps 5 and 7's populations, so it needs re-measurement.
- [ ] ~~Full suite, PR and CI green~~ deferred to ticket 06: the operator
  asked for a local proof and commit only, with no push or PR.
- [x] With the REIT ruling: adversarial 3 of 432 (step 5: 2, step 7: 1, HPS
  Net Lease Income REIT) (2026-09-25 06:10 ET).
- [x] Measured the missing evidence (2026-09-25 06:10 ET): every remaining violator (GPB
  Holdings II, Goldman Sachs REFT, Sculptor DREIT, HPS Real Assets Lending,
  HPS Net Lease Income REIT) has **no ticker**. "No ticker" alone would hold
  back 572 step-5 (10%) and 54 step-7 (5%) filers (utility subsidiaries,
  FHLBs, captive finance, pre-listing SPACs); "no ticker and an Emerging
  growth company category" holds back 171 and 44, and also catches unsampled
  private REITs (VineBrook Homes Trust, Invesco Real Estate Income Trust).
  The landing row carries no ticker (it is in `sec_company_ticker`), so either
  needs a new SEC contract version.
- [x] Operator (2026-09-25 06:34 ET): **option 1** (no ticker and an Emerging growth company
  category -> the record waits), done **after** a kind field is added to the
  Stage, so each waiting record says which kind it probably is.
- [x] **Probable Kind** on waiting Stage records (2026-09-25 06:54 ET). Operator: named
  Probable Kind, an estimate that sorts the Stage and never creates an
  identity (glossary). A deferred rule step may name one; a kind verdict not
  switched on is its own; GLEIF maps its categories (`probable_kind_values`);
  the waiting record keeps it (older ids unchanged); view
  `mdm_v2.stage_waiting` (migration 036, tested on a populated store). Also
  fixed: GLEIF's `RESIDENT_GOVERNMENT_ENTITY` (6,955 records) was refused as an
  invalid category. Unit: all new tests pass; the 8 known failures pin rule
  `.8`. PG16 clean suite: 133 passed; 4 known failures pin `.8`, 1 `fastapi`
  baseline. GoF pre-code consult: decide it in `normalize`, pass it at both
  writers.
- [x] Probable Kind split into its own PR, #711
  (`claude/company-mastering-12-probable-kind`, off `origin/main`), so it can
  land before rule `.10` (2026-09-25 07:10 ET). On main: 896 unit and 134 PG16
  clean tests pass. Its spec bullet was moved below the provenance paragraph
  it had split. When #710 is rebased after #711 merges, drop `cf95adbd`.
- [x] Three-axis `/code-review` of #711 (2026-09-25 07:25 ET). Fixed in `41ccddda`:
  - GLEIF records outside the approved scope now carry their Probable Kind
    (`category_kind`);
  - "older ids unchanged" is corrected: a record newly given a Probable Kind
    collides when its committed publication is re-read (the limit accepted
    on 2026-09-23).
  GoF: leave it. CI green on `41ccddda`.
- [ ] Merge #711 on the operator's word; then rebase #710 and drop `cf95adbd`.
- [x] #711 merged (`a8bfe004`, operator's word); #710 rebased onto main and
  `cf95adbd` dropped (2026-09-25 07:37 ET).
- [x] Ticker sources compared (2026-09-25 07:37 ET, `research/12-ticker-sources.py`). Bronze
  catalog `reference/sec/company_tickers_exchange/2026/09/02/` (sha256
  `836140c5…`, the newest in bronze) against each filer's own
  `submissions.json` tickers: 7,265 filers each, 7,077 in both (97.4%),
  188 in only one (mostly blank-check companies listing or delisting between
  the two dates). Option 1 with catalog tickers: 6,650 Companies (6,663
  with the filer's own), 91.28% of filers in the Stage (91.26%). The .10
  proof is measured with the catalog, the evidence the rule reads.
- [x] The SEC contract reads tickers (2026-09-25 07:37 ET): `prepare-clean-company` takes
  `--ticker-manifest`, the `sec_company_ticker` landing run, pinned beside the
  Company member (`tickers.parquet`); each record carries its CIK's tickers in
  rank order and the member's digest; the digest is in the publication key.
  Adapter `sec-company-landing-v3`. Unit: 1,477 pass, the 8 known `.8` pins
  fail.
- [x] Rule `.10` frozen and drawn (`8c450f25`): the ampersand fix, the SIC
  hold-back split in three with Probable Kinds, step 4 (no catalog ticker +
  Emerging growth), Company steps renumbered 8 and 10. Seed `20260925.10`.
- [ ] **Rule `.10` measured (2026-09-25 07:46 ET): cannot be approved.** Hand-read 1,261
  records (`12-10-label.py`). Sample 600 of 600; steps 8 and 10 each 300 of
  300, lower bound 0.991. **Adversarial: 2 of 561 violations, both step 8:**
  Sterling Real Estate Trust (private REIT, Form 10 in 2011, Form D; no
  ticker but not Emerging growth) and Terra Property Trust (non-traded REIT,
  Form 10, Form D; its catalog ticker is its listed notes). Step 4 holds
  back 381; of 100 read, 91 Companies (blank-check companies, start-ups,
  BDCs), 9 Funds: its Probable Kind is Company.
- [ ] Next rule: options measured (2026-09-25 07:46 ET, `12-options-11.py`). A: an
  `operating` REIT code with no ticker waits, and 6798 joins step 6; holds
  both, moves 64 Companies (mostly REIT operating partnerships) to the Stage.
  B: Form 10 + Form D + no N-54A + no ticker waits; needs forms evidence;
  holds Sterling only, moves 18. Operator chose **A**. Either needs fresh
  draws: the .10 draws designed both.
- [x] Rule `.11` (option A) frozen and drawn (`bcf3ffaf`): 6798 joins step 6;
  new step `6b` (operating REIT, no ticker); Probable Kind Company on 4 and
  6b; step ids kept stable (Company steps 8 and 10). Seed `20260925.11`; the
  2,898 filers of earlier draws left out of the adversarial arms.
- [ ] **Rule `.11` cannot be approved (2026-09-25 07:54 ET).** Reading the step 8
  adversarial arms found three Funds; reading stopped there, labels not
  written: Ellington Credit Co (now a registered closed-end fund: N-CSR
  2026-05-29, N-CEN, N-PORT; SEC still types it `operating`, REIT code,
  NYSE tickers); GPB Automotive Portfolio (private vehicle, Form 10 2021,
  Form D, no ticker, auto-dealer code; as GPB Holdings II); InPoint
  Commercial Real Estate Income (Form 10 + Form D, non-traded, listed
  preferred only; as Terra).
- [ ] Forms evidence measured (2026-09-25 07:54 ET, `12-options-12.py`): with .11, a step
  holding an `operating` filer with Form 10 + Form D and no N-54A, or one
  filing N-CSR/N-CEN/NPORT-P, stops all five Funds found in .10 and .11 and
  moves 171 more Companies to the Stage (91.58% of filers). The forms come
  from `sec_company_filing` (cik, form), landed by the same capture as
  `sec_company`. Operator (2026-09-25 07:57 ET): **yes, and work the checklist without asking at each step.**

### Rule version names (operator, 2026-09-25)

Each rule version has a descriptive name; the dated string stays in the
code as the digest's key.

| Name | Version | Adds |
|---|---|---|
| Legal-form rule | `2026-09-24.7`, `.8` | `other` filers need a code, a category and a legal-form word |
| Fund-name hold-back | `2026-09-25.9` | fund words, finance codes, no code |
| No-ticker hold-back | `2026-09-25.10` | no ticker + Emerging growth waits; `&` fix |
| REIT hold-back | `2026-09-25.11` | REIT with no ticker, or only Emerging growth, waits |
| Forms hold-back | `2026-09-25.12` | Form 10 + Form D without BDC, or fund reports, waits |
| Account hold-back | `2026-09-25.13` | ACCOUNT joins the fund-name words (an insurance separate account) |

### Forms hold-back checklist (`2026-09-25.12`)

- [x] GoF consult (2026-09-25 08:06 ET): extract `_pin_evidence` so each pinned member is
  one entry; share the count guard (`_within_counts`).
- [x] Primitive `values_overlap@1` (2026-09-25 08:06 ET), with tests and spec. Also: the
  ampersand fix had edited `token_match@1` in place, against the rule that a
  primitive is never edited; restored, and the fix is `token_match@2`, which
  the Company rule now uses.
- [x] The SEC contract reads `sec_company_filing` (2026-09-25 08:06 ET): `forms` per record,
  digest in `_origin` and the key; adapter `sec-company-landing-v4`; tests;
  local-operations doc.
- [x] Forms hold-back written (2026-09-25 08:06 ET): `7a` fund reports waits (Fund
  Structure); `7b` Form 10 + Form D + no N-54A waits (Company, from the
  full-population list; checked below).
- [x] Frozen and drawn (2026-09-25 08:06 ET), seed `20260925.12`: 600 sample, 320 fresh
  adversarial (3,722 earlier filers left out; the step 10 arms are spent:
  every member was read before, none a Fund), 104 held (all 4 at 7a, 100
  of 167 at 7b). 6,415 Companies, 91.58% of filers in the Stage.
- [x] Hand-read 1,024 records, labels written, scored (2026-09-25 08:08 ET,
  `12-12-label.py`). Sample 600 of 600; steps 8 and 10 each 300 of 300,
  lower bound 0.991. Held back: 7a 2 Funds of 4 (Fund Structure kept); 7b 2
  Funds of 100 (Company confirmed). **Adversarial: 0 of 320 if the TIAA Real
  Estate Account is a Company, 1 of 320 if it is a Fund.**
- [x] Operator (2026-09-25 08:10 ET): an insurance company's separate account **is a Fund**
  (glossary updated). Was: **Operator ruling needed:** is an insurance company's separate account
  (TIAA Real Estate Account: pooled real estate inside TIAA, sold to annuity
  holders on S-1, files 10-K, not a legal person) a Fund? It is the only
  such filer among the 6,415 Companies. If a Fund, add ACCOUNT to the
  fund-name words (moves exactly it) and draw fresh.
- [ ] ~~If it passes: PROOF with `by_step` and file hashes, `PENDING_ACTIVATION`
  on `.12`, update the tests that pin `.8`, full unit + PG16 suites, CI~~ deferred
  to the Account hold-back: the Forms hold-back failed on TIAA Real Estate Account.
- [ ] ~~Three-axis `/code-review` of the `.12` branch; fix findings~~ deferred
  to the Account hold-back: version `.12` was superseded before activation.
- [ ] ~~Plain-English `.12` approval brief and exact-digest approval~~ deferred
  to the Account hold-back: the operator classified the separate account as a Fund.
- [ ] ~~Activate `.12`, run four-company PG16, CI, and merge~~ deferred to the
  Account hold-back: the failed version cannot activate.
- [x] `.12` failed on the insurance separate account; the operator ruled it a
  Fund and `.13` was frozen and measured (2026-09-25 08:13 ET).

### Account hold-back checklist (`2026-09-25.13`)

- [x] Written and frozen (2026-09-25 08:10 ET): ACCOUNT joins `fund_name`; moves exactly the
  TIAA Real Estate Account. Seed `20260925.13`: 600 sample, 328 fresh
  adversarial (4,309 earlier filers left out; four new name-blind arms: no
  proxy, S-11, asset-backed reports, 13F), all 34 held at step 5.
- [x] **Passes** (2026-09-25 08:13 ET, `12-13-label.py`): sample 600 of 600 (lower bound
  0.9955); steps 8 and 10 each 300 of 300 (0.9911); **adversarial 0 of 328**.
  Held at step 5: 16 Funds, 18 Companies (13 BDCs); Probable Kind Fund
  Structure kept, noted as an even split.
- [ ] PROOF, `PENDING_ACTIVATION`, tests pinning `.8`, suites, CI.
- [ ] Three-axis `/code-review`; fix findings.
- [ ] Plain-English brief; **operator approves the exact digest**.
- [ ] Activate, four-company PG16 test, CI green; merge on the operator's word.
- [x] Handed to Codex with the PROOF and PENDING_ACTIVATION written; old `.8`
  tests still to update (`12-handover-to-codex-2.md`, 2026-09-25 08:14 ET).

### Codex completion checklist (Account hold-back)

- [x] Update the activation, source, and four-company tests to the frozen Account hold-back rule and its exact pending digest; keep the standard policy inactive (86 focused unit tests and three affected PG16 tests passed, 2026-09-25 08:33 ET).
- [ ] Verify the pinned research hashes and run MDM, architecture, and real PostgreSQL 16 Clean MDM tests without prerequisite skips.
- [ ] Push the reviewable branch, obtain green CI, and run Standards, Spec, and GoF reviews; repair any findings.
- [x] Write the Account hold-back brief with the pending digest, measured results, borderline readings, and limits (`12-approval-brief.md`, 2026-09-25 08:33 ET).
- [ ] Present the brief and obtain explicit approval of the exact rule fingerprint.
- [ ] Record the real approval time, activate only that approved digest, rerun the four-company PostgreSQL 16 test and CI, then merge on the operator's word.
