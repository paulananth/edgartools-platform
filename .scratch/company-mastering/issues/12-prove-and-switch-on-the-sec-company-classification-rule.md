# Prove and switch on the SEC Company classification rule

Type: task
Status: in progress
Blocked by: none (ticket 11 merged); activation now blocked by ticket 12 proof

## Question

Shell and ASML wait in the Stage because the standard SEC contract maps only
`entity_type = operating` to Company (ticket 11, gap 3). SEC calls a foreign
issuer `other`, as it does an individual; only the issuer carries an industry
code. The candidate rule `sec-company-candidate` says so, but a rule acts
alone only on a measured proof (§9.2) and the operator's approval of one exact
digest.

This is the **classification** part of ticket 05's Proving Run, carved out:
ticket 05 as written measures SEC-to-GLEIF matching and waits on ticket 08.
Ticket 06's approval is asked here for this one digest.

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
- [ ] Commit the proved failed gate and pending approval brief only on the
  Codex branch; do not push. Attempted at 2026-09-24 21:30 ET; `git add`
  could not create the worktree index lock under the shared repository's
  `.git/worktrees/codex-cm-12/` because this sandbox has read-only access
  there. All intended changes remain unstaged in this worktree.
- [ ] One change: SEC contract names the rule, plus its `automatic_rules`
  entry; four-company test shows Apple, Microsoft, Shell, ASML acting and
  Cook, Nadella deferred — blocked: step 4 is below 0.95 and the adversarial
  fixture has 33 violations. No activation entry may be added.
- [ ] Three-axis `/code-review`
- [ ] Full suite, PR and CI green
