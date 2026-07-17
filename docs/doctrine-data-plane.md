# Data plane doctrine (current)

**Accepted** doctrine for ingest, engagement, and agent consumption.  
Authoritative ADRs: [0001](adr/0001-agent-decision-surface-first.md), [0002](adr/0002-silver-soe-edgartools-exclusive.md).

If older docs (README medallion diagrams, data-architecture “always bronze”, companyfacts-must-bronze notes) conflict with this page, **this page and ADR 0002 win** until those docs are updated.

---

## One sentence

Ingest and engage through **silver**, fetch only via **edgartools** when silver + parser_version says miss, archive raw to **bronze** only on explicit request or when edgartools cannot provide the source; form trading decisions only from **Snowflake** projections of that state.

---

## Three systems of engagement

```text
SEC ──(edgartools only)──► Silver (runtime SoE)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
           MDM/graph      gold export     optional bronze
              │               │           (explicit / non-edgartools)
              └───────► Snowflake ◄───────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     Agent Decision Contract    Human Explore Mode
     (+ Agent View Mode)        (labeled not agent-grade)
```

| Plane | SoE | Not SoE |
| --- | --- | --- |
| Warehouse jobs | Silver | edgartools disk cache, ad-hoc SEC |
| Trading agent | Snowflake Decision Contract | Silver, bronze, Streamlit |
| Human audit of agent | Same contract (Agent View) | Explore free gold joins |

---

## Superseded ideas (do not re-introduce without a new ADR)

| Stale idea | Replacement |
| --- | --- |
| Always write bronze first | Default edgartools → silver |
| Companyfacts bronze required for agent-grade | Versioned silver facts skip; optional bronze |
| Artifact-in-bronze required for completeness | Silver parse success + parser_version |
| Parallel sec_client + edgartools forever | Hard cutover to edgartools-exclusive SEC I/O |
| Agent may read silver | Snowflake only for agents |
| Bronze once as default idempotency law | Silver once per parser_version; network on miss/force/bump |

---

## Still true (not superseded)

- SEC historical filing **bytes** do not rewrite; we simply **choose not to keep a second copy by default**.
- Discovery still needs network for **new** accessions / daily dates.
- Agent-grade still fail-closed on watermark mismatch, graph parity, coverage flags.
- ADV bulk and other **non-edgartools** sources still use **mandatory bronze** (or equivalent immutable store).
- Universe: warehouse ∩ MDM active; warehouse seed single writer (product grill).
- Issuer vs manager bundle shapes; 13F dual sections; pure-SEC features.

---

## Clarity backlog

See the “Needs clarity” list from the doctrine review session (cutover phasing, force semantics, parser_version authority, export table backlog, Explore whether Snowflake-only for humans). Resolve in `/to-spec`, not by silent code drift.

---

## Next engineering step

**`/to-spec`** — SecGateway, silver skip keys, bronze flags, Snowflake export delta, Decision Contract objects aligned with ADR 0001 + 0002.
