# Configured collection/join qualification

Status: delivered in PR #921, main 3a75cfd1; final reviewed head 5a823c48.
All six jobs pass in CI 38186218511. This is local/cached and installed CI
qualification, with no production deployment or activation claim.

Rust performs configured checks/filtering, typed-key grouping, stable scalar
ordering, canonical distinctness, first/last/one selection, missing matches,
nested joins and drops through source_engine.combine_tables. Python owns
input authentication/bounds, canonical callbacks, opaque payloads, output
encoding/bounds, receipts, publication and independent execute/verify.
Native scalar sorts release the GIL; Python object access/callbacks hold it.
The native binary participates in the existing runtime digest.

## Semantic and installed evidence

- 165 Rust tests and Python-feature type check pass. Initial 118 affected
  combination/nested/Company/reduction tests pass. After the Unicode correction,
  all 60 focused tests pass, including five literal native/public regressions.
- 1,500 exact comparisons against pre-port main cd277677, including 1,137
  identical exception classes/messages, stable order/types and unchanged inputs.
  Includes huge signed integers, exact bool/int/float distinction, signed zero,
  structured canonical values and escaped surrogate strings. See parity.json
  and reproducible parity.py; there is no runtime Python computation fallback.
- Independent Standards/Spec/GoF reviews are clear. Standards found early UTF-8
  rejection of surrogate metadata. Corrected injective surrogatepass tokens keep
  Python key/equality/order semantics; public escaped JSON execute/verify with
  dropped metadata passes. The reviewer separately checked 2,025 string pairs.
- 275 architecture/Company preparation/identity/survivorship checks pass.
- Local installed-bundle/real PG16 suite: 84 passes in 19m48s. Its installed
  fixture was pinned at initial cc13eef5; final corrected installation is
  separately verified by the final-head CI below.
- Final head CI: 926 engine passes, including installed bundle without checkout;
  648 MDM passes; 332 real PostgreSQL 16 integration passes and one existing
  xfail; unit/architecture and shell checks pass. Existing installed Company
  blueprint and active preparation callers plus combined-record parse/master
  recovery paths run through the native engine. Doctor resolves all 131 commands.
- Documentation audit confirms grammar, command examples, limits and authority
  unchanged. COMBINING records native computation and retained Python overhead.

## Bounded cached Company evidence

`company-40.json` records 40 deterministic receipt-pinned cached main documents
from cm05-7000, 20 two-document worker units, the pinned ticker catalog and the
whole cm27 census (43,245 names; materialized census reading 17,003,378 bytes).
Each unit's old/new output receipts and table digests match exactly. Both paths
execute, independently verify and repeat execution for lost-ack replay.
Source.read execute/verify also authenticates each input reading. Raw evidence
pins capture/census hashes, runtime files/native binary and script hash.

| Median per two-document unit | Python baseline | Native |
|---|---:|---:|
| Pure combination | 1.64276 s | 1.10660 s |
| Execute + verify + retry | 10.73534 s | 7.59006 s |

Observed ratios are 1.48x pure computation and 1.41x worker execute/verify/retry.
Twenty paired samples alternate execution order on a shared developer host with
other work active. These serial timings are provisional and do not establish
production or concurrent full-pipeline speedups. The combined-process peak RSS
is 703,520,768 bytes (671 MiB), including source-reading preparation and both
engines; it is neither a per-engine memory comparison nor an RSS cap. The
qualification step completed in 8m02s.

This is a placement/parity port. Whole-census authentication/decoding/grouping
costs remain, so preserve configured narrowing rather than repeating whole
materialized reads across every Company unit. Bookkeeping fan-in and admitted
Company orchestration are Claude's next slice. No new whole-census construction,
full population mastering, live SEC access or activation is claimed.

Reproduce from a checkout containing the pinned main baseline:

```bash
uv run --no-sync python .planning/workstreams/rust-configured-joins/parity.py \
  --output /tmp/join-parity.json
uv run --no-sync python .planning/workstreams/rust-configured-joins/qualify_company.py \
  --capture <cached-cm05-7000-path> --census <cached-cm27-census.json> \
  --limit 40 --output /tmp/company-join-40.json
```

The qualifier has an explicit bounded even `--limit` of 2..500 (default 40).
Measure broader workload/concurrency memory before deployment sizing. See
[HANDOFF-TO-CLAUDE.md](HANDOFF-TO-CLAUDE.md) for exact delivered interfaces and
remaining ownership boundaries.
