# Publication preparation qualification

Status: delivered by PR #925, merged as `7217f9c7` after all six CI checks
passed on reviewed head `d1cb80e2`. Independent review and qualification complete. Starting main `7f1e8856`; rebased without conflicts onto
`9bed91fd` and then `7dd6f5ab` (Claude profiling PRs #923/#924), with
identical implementation range-diffs. No production deployment
or activation is claimed.

## Implemented boundary

Rust constructs publication envelopes from immutable PostgreSQL JSONB text
behind the Python facade. It returns UTF-8 bytes directly to Python hashing and
decoding, avoiding a wide Unicode result copy. Store, JournalPublisher and the
public publication verifier read indexed `outbox_input` rows and compare the
complete bytes with the independently committed expected hash before sending.
Previously stored payloads retain their exact bytes. No payload copy is stored.

Migration 016 is additive/checksummed; old migrations and SQL APIs remain
compatible. The new claim locks the earliest outstanding consumer generation,
then checks the requested batch. Both old/new APIs share the same row, fence,
lease and history. Existing publication readers retain SELECT on the new view;
no write or claim privilege is copied. Program preparation does not replace
SQL freshness, policy/source authority, expected-hash derivation, lease/fence
checks or atomic batch/checkpoint/outbox persistence.

General JSONB normalization has an explicit 64 MiB budget. The publication
mode derives its allocation budget from authenticated stored parts, preserving
existing intent even when PostgreSQL numeric expansion exceeds compact request
size. Neither this nor a byte limit establishes an RSS cap.

## Verification

- 1,010 exact PostgreSQL/native text and SHA-256 comparisons, including arbitrary
  integers, numeric scale/exponents/signed zero, duplicate keys, control text,
  supplementary Unicode and 512 nested levels. Invalid SQL/native cases agree.
- 1,019 maintained MDM/architecture/real PG16 tests passed in 5m53s on the
  initial implementation; 110 post-rebase native/public and upstream profiling
  checks passed in 2m02s. Final byte path: 39 native/outbox/public worker checks
  passed in 53s; 20 final new PG16 checks passed in 12s, including an injected
  lost reply after durable verification: public execute/verify recovers the same
  receipt and the sink sends once.
- Restricted-role migration from a populated 015 store preserves request,
  payload and intent hashes; existing read-only publication login can read the
  new view, cannot claim or mutate. Mixed old/new concurrent claims preserve
  generation order and reject stale fences. Corrupt reconstruction is refused
  before sending and failure releases its claim. Existing pre-014 stored payload
  tests remain green. EXPLAIN uses existing batch/outbox indexes.
- Original Rust suite 168 passes; final library checks 7 passes and Python
  feature typecheck passes. Final native byte binding is loaded in the tests.
- Installed bundle at initial rebased `af100aa7`: 3 checks passed in 4m32s,
  covering installation without checkout, doctor, and real configured GLEIF
  publication/recovery. This precedes the byte-return refinement; final-head
  installed qualification is recorded separately below.
- Final code commit `a9cb9938` installed without checkout: all 3 publication
  preparation, doctor and configured GLEIF publication/recovery checks pass.
  Combined with all 58 upstream profiling checks, 61 passed in 6m07s. Later
  documentation-only evidence commits do not change this runtime.
- Doctor resolves 132 commands with engine loaded; store URLs unset during
  this command check. Skill validator passes; migration command help confirms
  `--application-role`. Operational instructions now include existing-store
  migration before using the new publication runtime. Frozen runtimes retain
  their original code/native binary.

## Final bounded cost comparison

`publication-200.json` and `publication-600.json` pin every relevant runtime
file, native binary, migration and qualifier. Both modes use separate fresh
Python processes and PostgreSQL 16 servers, with the same deterministic input
body/run ID. Each tests its own exact old/native payload/hash parity.

Each sample measures delivery, independent receipt/read-back verification and
a completed/no-work retry. Export uses the actual LocalContractSink; journal
uses the real JournalPublisher plus restricted Change Journal append/read-back.
The baseline journal implementation comes from pinned main `7f1e8856`; its
verifier query mirrors that public worker without adding an extra SQL hash.
Fault-injected lost acknowledgements are tested separately, not timed here.

| Records / consumer | SQL median | Native median | Client RSS SQL / native | PG sum RSS SQL / native |
|---|---:|---:|---:|---:|
| 200 / export | 0.197 s | 0.259 s | 89.0 / 101.7 MiB | 112.4 / 111.7 MiB |
| 200 / journal | 0.854 s | 0.645 s | 90.2 / 103.4 MiB | 161.3 / 113.9 MiB |
| 600 / export | 0.467 s | 0.567 s | 159.0 / 216.1 MiB | 143.5 / 138.2 MiB |
| 600 / journal | 2.275 s | 1.593 s | 165.1 / 218.5 MiB | 288.7 / 156.0 MiB |

All fixed placement criteria pass: median time/client RSS/server summed RSS
at most 1.5x SQL, claim bytes at most 1.1x, and unchanged SQL call counts.
Measured claim response bytes increase about 5.1%; export takes 5 MDM calls,
journal 8 MDM + 6 journal calls in both modes. Native preparation alone takes
about 1.5–11.8 ms on these inputs. Export costs 21–31% more wall time; accepting
that bounded cost moves preparation ownership into programs. Journal timings
are lower in these samples, without a production-speedup claim.

Memory is sampled every 10 ms during each mode's actions, separately from
setup and later parity probes. PostgreSQL sums include shared mappings more
than once and do not estimate physical unique memory. Runs are serial on a
shared development host, three repetitions, synthetic structured records,
not a production/concurrent full pipeline. Independent processes improve
comparability but do not eliminate host noise. The initial 600 export memory
failure (1.526x) was resolved by the UTF-8 byte path under the unchanged 1.5x
threshold; no acceptance limit was weakened.

Reproduce with MDM extras and the deliberate transient `pgserver` install:

```bash
uv pip install pgserver
LC_ALL=C PG16_SERVER=pgserver uv run --no-sync python \
  .planning/workstreams/database-computation-preparation/qualify.py \
  --limit 200 --output /tmp/publication-200.json
LC_ALL=C PG16_SERVER=pgserver uv run --no-sync python \
  .planning/workstreams/database-computation-preparation/qualify.py \
  --limit 600 --output /tmp/publication-600.json
```

The qualifier bounds `--limit` to 1..1000 and repeats to 1..10. Its acceptance
failure preserves the JSON evidence and exits nonzero. Remaining SQL
dispositions/prerequisites are explicit in DECISIONS.md; this is not blanket
retirement of every database expression or an analytics consumer cutover.

## CI correction

The initial PR CI run `38247132901` passed 941 engine tests and its unit,
architecture, MDM and shell jobs; integration reported 351 passes and one
expected failure, but failed the required self-describing-schema check. The
new view had its relation comment but lacked ten column comments and its new
claim function comment. Root reproduced that exact failure locally, added
comments without changing SQL logic, and all 25 maintained schema/new-publication
PG16 checks pass. Qualification was rerun for the changed migration checksum;
all four comparisons and runtime hashes were independently rechecked by
Standards/Spec. The table above is this refreshed evidence, not the earlier
18–20% export timing sample. Timing variation reinforces the local/shared-host
limitation. Final PR CI run `38248186788` passes all six checks; merge verified below.

## Verified delivery

PR #925 merged reviewed head `d1cb80e2` as `7217f9c7` on 2026-10-12
08:24 ET. CI run `38248186788` passed all six jobs: 697 unit, 258 architecture,
648 MDM, 352 PostgreSQL integration (one maintained expected failure), 941 engine
tests including the installed bundle, and 168 Rust tests. Shell lint and the
aggregate CI gate pass. The fetched main commit matches GitHub merge evidence.
No deployment, activation or live-store migration was performed.
