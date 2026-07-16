# Define Adviser-Fund Source Contract

- Type: research
- Status: resolved
- Blocked by: none
- Blocks: 21

## Question

Which authoritative IARD/IAPD or equivalent source, entitlement, acquisition process, and evidence contract will support complete `MANAGES_FUND` derivation at the Release Data Watermark?

## Exit criteria

- Select and approve the authoritative source.
- Define entitlement and acquisition preflight behavior.
- Define candidate identity, watermark, lineage, and completeness evidence.
- Define applicability, derivation, retry, and parity requirements.
- Assign implementation and release-acceptance owners.

## Resolution

Approved the public SEC/IAPD historical Form ADV Part 1 bulk filing data as the authoritative source, with the current IAPD compilation as the active-universe and latest-filing completeness control. The contract defines CRD/PFID identity, effective filing reconstruction, entitlement preflight, fail-closed outcomes, temporal derivation, and exact MDM/graph parity.

Decision artifact: [`docs/release-readiness/adviser-fund-source-contract.md`](../../../docs/release-readiness/adviser-fund-source-contract.md)

Implementation remains required under ticket 21; resolving this research ticket does not make `MANAGES_FUND` launch-ready.
