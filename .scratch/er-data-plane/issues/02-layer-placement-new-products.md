# 02 — Layer placement for new ER products

Type: grilling  
Status: resolved  
Blocked by: 01  

## Question

For each phase-1 product that **stores new data** (consensus, guidance, calendar, transcript), which layer is the system of record and what is published to agents: Gold only, Gold+MDM keys, Subject Bundle sections, and/or graph edges? What stays **External** (not ingested)?

## Answer

**Accepted full recommendation.**

| Product | System of record | Agents read | MDM | Graph | Subject Bundle | Notes |
|---------|------------------|-------------|-----|-------|----------------|-------|
| **ERDP-01 Consensus** | **Gold** fact table | Gold Explore SQL | Optional company/security key only | No | No (not pure-SEC / not Agent-Grade features) | Ingest to Snowflake plane; vendor may be upstream source |
| **ERDP-02 Guidance values** | **Gold** (8-K/earnings path, accession-linked) | Gold Explore | Optional company key | No | Phase-1: Gold only; optional later `latest_guidance` | |
| **ERDP-03 Earnings calendar** | **Gold** calendar table | Gold Explore | Optional company key | No | Phase-1: Gold only; optional later `upcoming_earnings` | |
| **ERDP-04 Transcript MVP** | **Object store** (bytes) + **Gold pointer** | Gold pointer; text via storage path | Optional company key | No | No phase-1 | Third-party source may feed store; SoR is platform pointer + optional copy |

**Cross-cutting**

1. Agent-Grade Decision Contract remains pure-SEC (ticket 03); new products are **Gold Explore** unless a later ticket adds Bundle sections with explicit grade rules.  
2. No Neo4j edges for estimates/calendar/transcripts in phase-1.  
3. MDM is identity only, not SoR for estimate/calendar/transcript content.  
4. ERDP-05 documents read paths for existing + new Gold tables.  
5. Market prices remain External (ticket 03).
