# Data plane doctrine (accepted target; implementation pending)

**Accepted** doctrine for ingest, engagement, and agent consumption.
Authoritative ADRs: [0001](adr/0001-agent-decision-surface-first.md), [0002](adr/0002-silver-soe-edgartools-exclusive.md), and [0006](adr/0006-sec-bronze-ledger-silver-authority.md).

ADR 0006 supersedes ADR 0002 only for optional-Bronze, default network-skip, and parser-upgrade re-download semantics. Existing runtime flags may still expose the legacy behavior until the change-propagation migration implements this target.

---

## One sentence

Authorize source requests in **PostgreSQL**, fetch SEC only through **edgartools**, verify every successful relevant response in immutable **Bronze**, publish business state to **Silver**, and form trading decisions only from aligned **Snowflake** projections.

---

## Authority and engagement planes

```text
PostgreSQL Change Ledger ──authorizes──► SEC via edgartools
          │                                  │
          │                                  ▼
          │                         immutable Bronze evidence
          │                                  │
          └────────controls processing───────┤
                                             ▼
                                Silver published business state
                                             │
                             ┌───────────────┼───────────────┐
                             ▼               ▼               ▼
                          MDM/graph      gold export      Snowflake
                             └───────────────┴───────────────┘
                                             │
                                Agent Decision Contract
```

| Plane | SoE | Not SoE |
| --- | --- | --- |
| Acquisition and processing control | PostgreSQL Change Ledger | S3 listings, workflow logs, Silver rows |
| Raw source evidence | Bronze | edgartools disk cache, mutable latest objects |
| Warehouse business state | Silver | Bronze, PostgreSQL lifecycle records |
| Trading agent | Snowflake Decision Contract | Silver, bronze, Streamlit |
| Human audit of agent | Same contract (Agent View) | Explore free gold joins |

---

## Superseded ideas (do not re-introduce without a new ADR)

| Stale idea | Replacement |
| --- | --- |
| Optional Bronze on successful source responses | Mandatory verified Bronze evidence before processing |
| Silver/parser version decides whether to call SEC | PostgreSQL Source Fetch Decision backed by verified evidence and policy |
| Artifact-in-Bronze alone proves completeness | Exact ledger binding plus checksum, capture finalization, and scope proof |
| Parallel sec_client + edgartools forever | Hard cutover to edgartools-exclusive SEC I/O |
| Agent may read silver | Snowflake only for agents |
| Parser bump forces network acquisition | Reprocess verified Bronze; redownload only for missing, corrupt, incomplete, or repaired evidence |

---

## Still true (not superseded)

- SEC historical filing **bytes** are immutable; contradictory bytes under one identity fail closed and both artifacts remain evidence.
- Discovery still needs network for **new** accessions / daily dates.
- Agent-grade still fail-closed on watermark mismatch, graph parity, coverage flags.
- ADV bulk and other approved source families also require immutable Bronze evidence.
- Universe: warehouse ∩ MDM active; warehouse seed single writer (product grill).
- Issuer vs manager bundle shapes; 13F dual sections; pure-SEC features.

---

## Clarity backlog

See the “Needs clarity” list from the doctrine review session (cutover phasing, force semantics, parser_version authority, export table backlog, Explore whether Snowflake-only for humans). Resolve in `/to-spec`, not by silent code drift.

---

## Capture modes

See [capture-modes.md](capture-modes.md) for the legacy `normal` versus `strict_release` runtime flags that remain until this target is implemented.

## Next engineering step

Implement tickets under `.scratch/agent-decision-data-plane/issues/` (frontier: 01–02, 08, 14 completed in phase 0).
