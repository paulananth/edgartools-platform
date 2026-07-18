# Confirm destination and old-data decay principle

Type: grilling
Status: resolved
Blocked by: 01
Blocks: 08, 09, 10, 11
Assignee: grok-session

## Question

Do we lock the map destination as: **per-document usefulness timelines for
agent-first GO**, with principle **old data has less value for current-at-watermark
agent decisions**, while multi-year **financial feature inputs** stay on the
companyfacts/gold path — not relationship document history?

## Exit criteria

- Explicit yes/no on agent-first vs full-regulatory-history-first destination.
- One sentence principle for decay (step lookbacks vs continuous decay).
- What “investment research” means for this map (features vs Explore archive).

## Answer

**Destination locked: agent-first GO.** Per-document usefulness timelines serve
current-at-watermark agents first; full regulatory-depth archives are not
required for first agent-useful PASS.

**Decay principle (one sentence):** Encode “old data has less value” as **hard
step lookbacks per form family** (not continuous age scores, not full-history
defaults).

**Investment research (two layers):**
1. **Quant analysis** (CAGR, growth, earnings potential) → companyfacts → gold
   As-Of Decision Features (multi-year FY *inputs* to one as-of row) — **not**
   Ticket 20 relationship document depth.
2. **Human Explore** → optional deeper relationship/filing archives, labeled
   not agent-grade — **not** required for agent GO.

Downstream window-lock tickets (08–11) must fit this destination; freeze rebuild
must not use a single global 2013 start for every form.

## Grill log

| # | Decision |
| --- | --- |
| 1 | Agent-first GO (not full-regulatory-history-first) |
| 2 | Step lookbacks per form family |
| 3 | Research = quant features path + optional Explore archive |
