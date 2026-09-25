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
- [ ] Operator: are private REITs that register by Form 10 Funds or Companies?
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
