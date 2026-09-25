# Prove and switch on the SEC Company classification rule

Type: task
Status: in progress
Blocked by: 11

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
- [x] Freeze the rule: version 2026-09-24.6 (industry codes 6189, 6221, 8888
  wait; `operating` is a Company; `other` needs an industry code and a
  legal-form word, and a person's suffix waits) (2026-09-24 20:18 ET)
- [x] Label a simple random sample of the rule's `company` verdicts from
  evidence the rule does not read; adversarial fixture of individuals, funds
  and every individual with an industry code; script, sample and SHA-256s
  committed — `research/12-*` (2026-09-24 20:22 ET)
- [x] Wilson lower bound: 297 of 300, **0.97524**; step 2 0.97395, step 4
  0.93931; adversarial 294, 0 violations (2026-09-24 20:22 ET)
- [ ] Operator approves the exact policy digest (ticket 06), or not
- [ ] One change: SEC contract names the rule, plus its `automatic_rules`
  entry; four-company test shows Apple, Microsoft, Shell, ASML acting and
  Cook, Nadella deferred — PG16
- [ ] Three-axis `/code-review`
- [ ] Full suite, PR and CI green
