# Inventory Atlas Free limits versus Decision Graph Bundle size

Type: research
Status: resolved
Blocked by: none

## Question

Can Atlas Free (M0) hold v2 agent documents for a realistic issuer set,
or does 512 MB / 500 connections / 100 ops/s / 10 GB week transfer force
a subset or a paid cluster before v2 is useful?

Estimate from **primary sources**:

1. Official M0 limits (storage, connections, ops/s, transfer, one free
   cluster per project, no peering/PrivateLink).
2. In-repo Decision Graph Bundle / Feature Screen payload shape
   (`build_issuer_subject_bundle`, `build_subject_feature_screen`,
   watermark dict). Size one issuer document (features + insiders +
   employment + coverage + watermark) from code and, if cheap, a fixture
   or live 21-CIK factor row count — not a full prod dump.
3. How many such documents fit in 512 MB at that size, versus 21 sample
   CIKs versus ~63k MDM-active.
4. Whether `0.0.0.0/0` plus TLS + DB user is the documented public-agent
   path, and what Atlas warns.

Read-only. Do not provision Atlas. Do not implement.

Save findings at
`.scratch/mongodb-v2-agent-interface/research/01-atlas-free-vs-bundle-size.md`.

## Answer

**M0 can hold a useful v2 of the 21-CIK sample, and a sparse ~63k
one-doc-per-issuer collection. It cannot hold 63k Apple-dense
neighborhoods in 0.5 GB. A single Feature Screen document for the
universe is illegal on every tier (16 MiB BSON).**

Official Free cluster: 0.5 GB storage (BSON+indexes), 500 connections,
100 ops/s, 10 GB in/out per 7 days, one cluster per project, no
peering/PrivateLink, public `mongodb+srv`, TLS required, DB user
required. `0.0.0.0/0` is documented with a credentials warning and
email alert. Clusters never expire; idle may pause after 30 days.
BSON max 16 MiB is a server limit, not M0-only.

Measured (synthetic Apple-like issuer, 20 insiders, 30 employment,
FY+interim 19 keys): ~12.0 KiB JSON / 12.5 KiB BSON. One Feature
Screen row ~1.5 KiB JSON. 21-CIK screen ~29 KiB BSON. 63k-row single
screen ~82 MiB BSON (~5× over 16 MiB; cap ≈ 12.4k full rows).

Capacity: 21 CIKs trivial. Sparse 63k (today’s 87 insiders / 1,351
employment / 21 features) ~150–210 MiB with indexes — fits. Dense 63k
Apple-sized ~0.75–1.1 GB — does not. Paid is not a prerequisite for
21-CIK or sparse-universe v2.

Findings:
[research/01-atlas-free-vs-bundle-size.md](../research/01-atlas-free-vs-bundle-size.md)
