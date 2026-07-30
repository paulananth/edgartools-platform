# Define the Direct-Evidence GO Packet

Type: grilling
Status: resolved
Blocked by: 01, 05, 06, 07, 09, 25

## Question

What final packet structure, evidence index, signer sequence, expiration/freshness rule, and fail-closed decision logic must be complete before the Release Owner may record GO without conditional or accepted-basis exceptions?

## Answer

### One packet, with preserved attempts

The Candidate Evidence Set defined by ticket 01 is the sole Direct-Evidence GO
Packet. Do not create a second summary or restate gate results in another
authoritative artifact. Its top-level `release-evidence.json` is the
authoritative manifest; `full-chain-launch-pass.json` is its ordered eight-gate
index.

One immutable Release Candidate may contain multiple append-only Evidence
Attempts when evidence expires or a gate fails without changing the integration
commit or either image digest. Each attempt has exactly one Release Data
Watermark. Failed or stale attempts remain preserved and are explicitly
superseded by a later attempt; their records are never overwritten or silently
promoted. A commit or image-digest change still requires a new candidate.

The packet has three validator-derived readiness states:

1. `not_ready` — evidence is incomplete, invalid, stale, unauthorized, or
   internally inconsistent;
2. `ready_for_owner` — one active attempt satisfies every automated predicate,
   the disposition remains unset, and the Release Owner may decide;
3. `go_verified` — the owner recorded GO and the Release Seal verifies against
   the exact finalized evidence commit.

Human `no_go` and `superseded` dispositions are terminal decisions, not
validator-inferred readiness states. Automation must never convert a missing
artifact into NO-GO, a warning, a conditional pass, or an accepted-basis pass.

### Exact gate index and attestations

Every Evidence Attempt contains exactly one active indexed record for each of
these eight gates, in order, and no unknown gate:

| # | Required gate | Required attesting role |
|---|---|---|
| 1 | Candidate Identity Binding | Candidate Builder |
| 2 | Rollback Readiness | AWS Operator |
| 3 | MdmExport Entitlement Preflight | MDM/Graph Operator and Snowflake Operator |
| 4 | BatchSilver MaxConcurrency=4 and Data Integrity | AWS Operator |
| 5 | Required Relationship Source Completion | AWS Operator |
| 6 | MDM, Export, and Graph Execution | MDM/Graph Operator and Snowflake Operator |
| 7 | Relationship Eligibility and Exact Parity | MDM/Graph Operator |
| 8 | Release-Bound Dashboard Acceptance | Dashboard Reviewer |

One gate record may index multiple sanitized, digest-bound artifacts and
multiple required attestations. Extra non-gate material may appear only as a
non-authoritative addendum reference. It cannot satisfy, replace, or override a
gate.

Rollback Readiness is the sole standing-evidence exception: the attempt indexes
the current standing proof from ticket 05 and proves that its rollback
mechanism identity matches the candidate's mechanism. It is not copied into the
attempt, rebound to its watermark, or expired by the 24-hour clock.

### Authority and signer sequence

Signer authorization comes from a version-controlled Release Authority Registry
outside the Candidate Evidence Set. The candidate records the registry version
and digest used at identity freeze. The registry maps each logical role to
stable approver handles and signing-key fingerprints. The packet cannot add or
authorize its own signers. Any registry change after identity freeze requires a
new Release Candidate.

One person may hold multiple logical roles, but each required gate attestation
is a distinct signed action for that role. The causal sequence is:

1. Candidate Builder freezes candidate identity and the authority-registry
   digest.
2. Candidate-specific gate evidence is captured and committed for one attempt.
3. Every required gate owner attests that gate's evidence digest, candidate
   identity, and attempt watermark.
4. Automation validates the active attempt as `ready_for_owner`.
5. Release Owner records a separate GO attestation over the complete packet.
6. The finalized packet is committed; the Release Owner creates the expected
   signed annotated Release Seal tag.
7. Independent validation verifies the authorized signature and confirms the
   tag targets that exact finalized evidence commit. Only then is the result
   `go_verified`.

The Release Owner is not an additional gate attester and cannot waive a missing
gate-owner attestation.

### Freshness and chronology

The verified Release Seal timestamp anchors the fixed 24-hour Live-Evidence
Window. Every candidate-specific evidence capture, gate attestation, and Release
Owner attestation for the active attempt must fall within the preceding 24
hours and share that attempt's Release Data Watermark. The chronology must
satisfy:

```text
identity freeze
  <= evidence capture
  <= corresponding gate attestation
  <= Release Owner GO attestation
  <= verified Release Seal timestamp
```

The standing rollback proof remains valid by exact mechanism match and has no
calendar expiration. All other expiry, digest, lineage, watermark, chronology,
secret-scan, role-authorization, and signature checks fail closed.

### Scope boundary and implementation consequence

This packet decides production operator readiness only. The F1-F12
customer/product promotion criteria are tracked work outside this operator GO
predicate; ticket 25's resolved scoping decision is sufficient and tickets
28-39 do not become hidden ninth-through-twentieth GO gates.

The current Release Evidence Automation deliberately returns
`go_validation_not_implemented` and its schema does not yet model Evidence
Attempts, the authority-registry binding, this exact gate/role matrix, or seal
verification. Ticket 48 owns that implementation. Until it is implemented and
verified, no Candidate Evidence Set can reach `ready_for_owner` or
`go_verified`.
