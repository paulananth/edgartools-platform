# Silver system of engagement; edgartools-exclusive SEC I/O; optional bronze

**Status:** accepted  
**Supersedes (hot path):** default “always bronze first,” “companyfacts bronze required for agent-grade,” and “artifact present in bronze” as the primary idempotency/agent completeness signal.  
**Complements:** [0001-agent-decision-surface-first.md](0001-agent-decision-surface-first.md) (agent still consumes **Snowflake** projections; this ADR defines **ingest** doctrine).

## Doctrine (one sentence)

Ingest and engage through **silver**, fetch only via **edgartools** when silver + parser_version says miss, archive raw to **bronze** only on explicit request or when edgartools cannot provide the source; form **Trading Decisions** only from **Snowflake** projections of silver / MDM / graph / gold state.

## Three systems of engagement

| Plane | System of engagement | Used by |
| --- | --- | --- |
| **Runtime / ingest** | **Silver** (DuckDB warehouse state) | bootstrap, incremental, parsers, MDM readers of SEC silver |
| **Agent decisions** | **Snowflake Decision Contract** (exports of silver/MDM/graph/gold) | trading agents; Agent View Mode |
| **Human exploration** | Snowflake gold (and related) under **Explore Mode** labels | analysts; never agent-grade inputs |

Agents and Agent View Mode **must not** query silver/DuckDB or raw SEC.

## SEC I/O

- **edgartools is the exclusive warehouse gateway** for SEC network access covering objects the library can supply (filings, catalogs, companyfacts, tickers, etc. as adapters are completed).
- **Hard cutover target:** remove parallel `sec_client` (or equivalent) downloads for the same objects; migration may be phased in tickets but the end state is exclusive.
- **edgartools local disk cache is not SoE** across ECS tasks; only silver (and optional bronze archive) is shared durable state.
- **Parse helpers** in edgartools (e.g. `Ownership.from_xml` on bytes already in memory for a capture run) remain allowed; they are not a second network path.

## Idempotency (silver once per parser version)

Default skip network when silver already has successful work for:

| Work | Skip key (conceptual) |
| --- | --- |
| Form-family parse | accession + form-family + **parser_version** |
| Companyfacts / entity facts | CIK + **facts_parser_version** (or equivalent) |
| Daily index | business date finalized in silver checkpoint |
| Submissions / filing list | sync completeness; network only to discover **new** accessions/dates |

`--force` re-calls edgartools and overwrites silver (and bronze only if persist was requested).

Parser / edgartools upgrades that bump version **may** re-hit SEC for affected keys — accepted cost of not retaining default raw copies.

## Bronze (narrowed)

| Write bronze? | When |
| --- | --- |
| **No** (default) | Normal capture and re-runs |
| **Yes** | Operator **explicit** request (`--persist-bronze`, env, or dedicated archive job) |
| **Yes** | Source **not available via edgartools** (e.g. IAPD Form ADV Part 1 public bulk, PCAOB bulk, other approved non-library inputs) |

Bronze is an **optional raw archive**, not the hot path and not required for Agent-Grade Reads unless that archive was part of an explicit evidence policy.

## Agent-grade completeness (no default bronze)

Agent-Grade Reads pin, at minimum:

- silver-derived **parse / facts parser versions** and section completeness (empty vs unavailable)
- filing-spine and daily catch-up claims as **silver checkpoints** (not bronze file presence)
- **gold run_id** / feature as-of
- **graph generation** + parity proof (verify-graph or equivalent)
- **Decision Contract Version** and composite **Decision Watermark**

Raw document sha256 is included **only** when bronze persist was used for those objects.

## Relationship to gold and MDM

- Silver remains the engagement surface for **warehouse** mutation and MDM **source** reads until those sources are exported.
- Anything the **agent** needs must still be **published to Snowflake** (expanded gold/export and/or MDM graph export). Silver SoE does not authorize agent→DuckDB.

## Consequences

- Refactor loaders toward a single **SecGateway** (edgartools + silver skip).
- Update runbooks and architecture docs that still say “immutable bronze is always written first.”
- Companyfacts: no mandatory bronze on the default path; versioned silver skip instead.
- Storage and SEC traffic trade-off: less default S3 raw volume; more SEC traffic on parser upgrades.
- Operator archive remains available when legal/audit/research **explicitly** asks.

## Open items (clarity backlog, not undecided doctrine)

- Phased inventory of every non-edgartools call site for hard cutover tickets.
- Exact operator flag names and non-edgartools bronze allowlist.
- Parser_version authority (library version vs internal PARSER_VERSION constants).
