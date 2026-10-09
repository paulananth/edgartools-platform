# Codex to Grok: whole-source Name Frequency

## Current status

PR: https://github.com/paulananth/edgartools-platform/pull/886
Branch: `codex/whole-census-eof-20261009`
Base: `51fe80b0` (merged #881, #884 and #885).
Worktree: `/private/tmp/edgartools-platform-codex-whole-census-eof-20261009`.

Operator handoff to Grok: 2026-10-09 13:41 ET. The operator explicitly requested making
this PR ready with its pending work documented. **Ready for review does not
mean original-EOF qualification or the broader goal is complete.** Codex hands
over the remaining work below; the ongoing scan is left running.

Full CI gate [37958542228](https://github.com/paulananth/edgartools-platform/actions/runs/37958542228)
is green on `ae627570`. PostgreSQL integration: 309 passed, one expected failure,
no prerequisite skips. This handoff/receipt commit triggers another full gate.

At handoff, the scan has matched **2,400,000 / 3,428,477 records**, with no
reported differences. Last measured scan time: **5,672.245 seconds (94m32s)**.
The initial 73-minute prefix-based estimate was exceeded; recent throughput
projects about another hour. This is an equivalence qualification including
both configured projection and the retained independent oracle.

## Implemented slice

- Generic typed projection, declared data-shape recovery, sequence, bounded
  line/token/slice text operations; immutable interpreter feature/recipe caches.
- GENERAL mapped fields and current quality/eligibility observations, global
  addresses before candidate or eligibility filtering, source ordinals and
  scoped holder state. Every one of the seven current cascade passes is kept.
- Generic input-bound context/lookup derivation through complete authenticated
  producer Source Extracts, including late-partition validation and bounds.
- Bundled projection Rules and reproducible offline qualification drivers.
  Generator `--check` proves exact output equality without modifying Rules.
- Source Extract and Name Frequency are the agreed prose names. Existing wire
  keys, filenames and manifest identifiers remain stable.

## Verified upstream and review evidence

All 69 complete SEC captures contain 43,338 filers and derive 43,245 wanted
keys. Configured publisher metadata derives 3,428,477 GLEIF records. Publication
authority remains separately bound to its pinned manifest.

Company/former-name SHA values match the historical Name Frequency capture
pins. Address and manifest bytes have authenticated immutable qualification
receipts; the historical Name Frequency had no address pins, so historical
address authentication is not claimed.

Local verification: 161 native cases; 299 affected cases before the isolated
resource-budget correction; all 51 targeted cases on the corrected extension;
58 genericity checks; exact Rules regeneration; corrected native extension
agrees on all rows of a 1,000-record bounded captured sample. The green CI gate runs the full
suite against the corrected committed code build.

Independent specification review found no blocking deviations. Standards
review found omitted projection node/depth accounting, reproduced it with
100,001 empty arrays, and confirmed the corrected counting and regressions.
Generator helper names were clarified and byte checks added. No class
hierarchy or source-specific production loader was introduced.

## Immediate pending work — Grok

- [ ] Monitor the **existing** scan through original EOF. Log:
  `/private/tmp/codex-census-eof-full.log`; executed script:
  `/private/tmp/codex-census-eof-full.py`; Codex tool session `18212`.
  That session ID belongs to Codex tooling; use the log and output files from
  another runtime. Do not launch another scan while this one is active.
- [ ] Verify the resulting
  `/private/tmp/codex-census-eof-proof/whole-source-eof-comparison.json`:
  `original_source_eof`, exact 3,428,477 records and 13,252,301,819 expanded
  bytes; complete projected rows, Name Frequency entries, global address
  occurrence counts, scoped last occurrences and all seven cascade passes
  must agree. A prefix or progress log is insufficient.
- [ ] Record the complete report, Name Frequency receipt and global-address
  digest in committed evidence; stamp the EOF checklist only after verified.
  Preserve complete outputs locally, including `complete-name-frequency.json`
  and `global-address-frequency.jsonl`.
- [ ] Record the exact qualified runtime. The ongoing pass uses the immutable
  v2 native build corresponding to `1861f1a1`. The later refusal-budget fix
  `ae627570` is separately verified by 161 native tests, 51 targeted tests,
  CI and a 1,000-record captured comparison on v3. Preserve this distinction;
  full v3 archive execution/replay is not yet qualified.
- [ ] Review PR886 and the final documentation CI, reconcile the checklist,
  and decide its disposition. Make any changes on your own `grok/` branch.

Do not modify the Codex worktree's watched Rules, Python runtime files,
executed scan script, native v2 extension, `sec-proof.json` or
`publication-proof.json` before the running pass completes its final hash
check. These are all pinned. The scan is direct interpreter/oracle comparison;
its completion does not qualify full worker execute/replay or installed MDM.

## Broader original goal — still incomplete

Original goal: self-sustaining installable skills, bundled Rules creator,
configuration-driven parsing and MDM orchestration, approved custom parsing
only for demonstrated gaps, and complete old-parser retirement. The goal
tracker currently reports `usageLimited`; it has not been marked complete.

Existing installed bundle, Rules creator and bounded worker parse/prepare/merge
proofs are already recorded under `data-skill-completion/TICKET.md` (merged
#805/#806/#807). Preserve those accomplishments. Remaining work is:

- [ ] Complete whole-source configured reduction/composition and bundled
  construction at actual population scale. The generic reduction grammar and
  captured-prefix subtraction/last-occurrence proofs exist; full state/output
  limits, cross-table candidate composition and complete worker results need
  qualification. Incremental traversal and direct EOF comparison alone do not
  close this gate.
- [ ] Complete approved capture/catalog run-ID bindings, receipt-bound Company
  classification, provenance, catalog joins and preparation semantics. Keep
  pagination, identity, address and recovery contracts independently failing.
- [ ] Qualify full installed-bundle orchestration outside checkout with
  independent worker/verifier processes and fresh restricted PostgreSQL16:
  **6,414 Companies / 3,052 CIK+LEI bindings**, unchanged second pass and recovery.
  The existing small fixtures do not replace this population proof.
- [ ] Switch remaining active Company/GLEIF construction, record interpretation,
  preparation and mastering callers to the qualified configuration route.
- [ ] Complete remaining Company/GLEIF adapter mapping and generic configured
  capture qualification. Preserve `sec_client` until `provider.capture` is
  qualified; do not revive the retired archive inspector.
- [ ] Prove no executable callers remain, then delete obsolete runtime parsers,
  constructors and unused caller-specific tests. Retain independent test-only
  oracles until equivalent positive, failure, transport and recovery coverage
  is established.
- [ ] Reconcile the older Person read-block/equivalence requirements against
  current merged code and actual proofs. Read blocks exist; their historical
  unchecked trackers do not establish completion. **New Person feeds are
  outside this operator slice and remain deferred.**
- [ ] Finish the installed self-sustaining skills/Rules-creator/orchestration
  audit, examples, command/link drift and requirement mapping; reconcile parent
  issue20 L3–L8 and the original source checklists against live merged evidence.
  Custom code requires a demonstrated configuration gap and operator approval.
- [ ] Resolve the attestation ticket's two still-open verification/acceptance
  lines separately using evidence. This slice leaves them open and keeps #881
  closed; do not redo its merged implementation.

Authority: `whole-source-census/TICKET.md`, `data-skill-completion/TICKET.md`,
`company-configured-preparation/TICKET.md`, `gleif-configured-reading/TICKET.md`
and `configured-archive-attestation/TICKET.md`. Older unchecked trackers must
be reconciled before assuming their implementations need to be repeated.

This is a backlog handoff, **not authorization to start the installed proof,
Person feeds, deployment, active cutover or parser deletion now**. The original
operator boundaries below remain in force. Finish the EOF gate first.

## Boundaries for Grok

Grok now owns the pending review/qualification follow-through. Review this
slice and its evidence from your own `grok/` branch/worktree.
Do not commit to the Codex branch or use the dirty primary checkout. Run
`bash scripts/dev/overlap_guard.sh` before every commit and push; stop on overlap.
The protected attestation branch remains stopped; do not restore
`gleif_source.inspect_archive`. PR881 publication checks already use generic
attestation, and this slice does not close its two still-open ticket lines.

The following remain open and were not scheduled or performed:

- Installed empty restricted PostgreSQL16 proof of 6,414 Companies and 3,052
  CIK+LEI bindings, unchanged replay and recovery.
- Full archive-scale `source.read` worker execute/replay and independent-process
  verification; direct interpreter EOF comparison is a distinct proof.
- Active caller replacement and obsolete parser/construction deletion.
- Installation, hosted deployment, Person feeds, Security mastering and Claude's
  profiling program/ticket 07c.

See `TICKET.md` for the still-open broader parent goal. No deployment or merge
is included in this handoff.

## Reproduction

See `crates/source-contract/tests/qualification/README.md`. Preserve the local
output directory `/private/tmp/codex-census-eof-proof`. Inputs are cached and
pinned; qualification makes no SEC requests. Source/runtime/Rules files used by
a running scan must remain immutable until its final hash check completes.
