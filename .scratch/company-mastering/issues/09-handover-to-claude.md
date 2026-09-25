# Ticket 09 handoff to Claude: dated Company read authority

Written by Codex, 2026-09-25 18:34 ET. This is a work handoff, not a claim
that the Company milestone is complete.

## Exact handoff point

- PR [#714](https://github.com/paulananth/edgartools-platform/pull/714) is a
  **non-draft**, open PR from `codex/company-mastering-09-10` to `main`. Check
  its live head and CI before acting; this note does not authorize merging it.
- Codex owns that branch and its worktree at
  `/Users/aneenaananth/projects/edgartools-platform-worktrees/codex-cm-09-10`.
  Claude should cut a new `claude/<topic>` branch in its own worktree from the
  merged `main`, never commit to Codex's branch.
- The Company policy fingerprint remains exactly
  `983352e81d295a165a1391e82fa8a24a710e6f638361a577f18f541917fd4049`.
  Only Account hold-back is active. The declared Name-and-state and Postcode
  with state veto rules are still off. The CIK rules are also off; do not infer
  activation approval from this PR.

## What is implemented and proved locally

- Migration 037 creates `mdm_v2.company` with dated versions and named
  identifying columns, plus `company_alias` for immutable-ID routing. A
  projection trigger writes the dated row in the Merge Stage transaction;
  the migration backfills historical Company versions on a populated store.
  `valid_from` is the recorded MDM decision time, not source effective time.
- Company API and snapshot pages read the dated table. New durable publication
  intents resolve Company bodies from it. Delivery also rebuilds Company
  bodies from dated rows at the intent's generation, including for pending
  intents created before migration, and refuses drift from the durable hash
  or named identifying columns. Export and graph share that path.
- SEC business and GLEIF legal addresses are each one structured value;
  source priority selects a whole value, retaining the other as disagreement.
  GLEIF additional legal-address lines survive. A selected clear is SQL NULL.
  The GLEIF Level 1 default source name is `gleif.level1.v1`; an arriving
  Company source absent from the priority list fails the batch.
- Local checks at the final code state: **154 PostgreSQL 16 Clean integration
  tests passed without skips in 11m49s**; **1,668 MDM/architecture tests
  passed**; the 56 focused source tests, Ruff and `git diff --check` passed.
  Standards and Spec rechecks found no remaining concrete defect; GoF review
  found no justified pattern refactor. This is local proof, not Snowflake or
  production qualification.

## Next Company work

1. [Ticket 10](10-make-the-stage-latest-only.md): implement latest-only Stage
   and compact decision receipts with exact bronze references. Its design is
   settled in the ticket; no migration or runtime change has been made. The
   current Stage and `batch.effects` still retain full assertion history.
2. [Ticket 14](14-carry-sec-country-code-into-silver.md): carry SEC
   `countryCode` from bronze through silver and Company matching evidence.
   Shell and nine other postcode matches wait on it.
3. [Ticket 13](13-correct-an-incorrect-company-link.md): fix wrong-link
   correction and quarantine before activating the two name rules.
4. [Ticket 15](15-approve-and-activate-cik-binding-rules.md): close ticket 04
   safety items, prove the Identifier Contract, and obtain separate approval
   for the exact activation fingerprint. Then complete tickets 05/06's whole
   proving run and separate name-rule activation decision.

Ticket 09 remains `claimed` because dynamic policy distribution through the
Rules Database and re-reading any store with older Company field names are
still unchecked. No live Clean Company evidence is known to require that
older-name migration; the approved path is a fresh rebuild from pinned input.
The new address mapping needs a versioned mapping registration if applied to
an already populated source registry. Do not treat the local tests as approval
to switch on matching, cut over consumers, or start another entity kind.
