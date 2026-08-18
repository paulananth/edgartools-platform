# 01 — Classify all 18 install.sh stages into provision / deploy / early-data / late-data

Type: grilling
Status: resolved
Blocked by: none

## Question

Assign each of `build_stages()`'s 18 stages to exactly one of the four
phases (provision, deploy, early-data, late-data), producing the
definitive classification Tickets 02-04 build on.

Draft classification (from reading each stage's own inline comment in
`infra/scripts/install.sh`), for reaction rather than blind adoption:

| # | Stage | Draft phase | Why |
|---|---|---|---|
| 1 | AWS: Terraform state bucket | provision | bare infra bootstrap |
| 2 | Snowflake: Neo4j Native App install | provision | infra prerequisite; also has its own placement rule (must precede stage 13) |
| 3 | AWS: passive infrastructure | provision | VPC/S3/ECR/ECS cluster/etc. |
| 4 | AWS: access roles/policies | provision | IAM roles/policies |
| 5 | AWS: ECR image publish | deploy | application image artifacts |
| 6 | AWS: ECS task definitions and Step Functions | deploy | application deploy |
| 7 | Snowflake: native-pull foundation | **ambiguous** — creates DB/schemas/warehouses (provision-flavored) but also integration/pipe/stream/procedures/task (deploy-flavored) |
| 8 | AWS/silver: seed-universe (full/unscoped) | early-data | real SEC data fetch |
| 9 | Snowflake: MDM export targets | deploy | empty-table DDL, no data |
| 10 | Snowflake: dbt gold | deploy | builds transformation models |
| 11 | Snowflake: loader role ownership | **ambiguous** — access-control provisioning, but tightly coupled to stage 10's output (dynamic tables must exist first) |
| 12 | Snowflake: Streamlit dashboard | deploy | application artifact upload |
| 13 | Snowflake Postgres / graph prerequisites | **ambiguous** — provisions the MDM Postgres instance/schema (provision-flavored) but is really a prerequisite for late-data's MDM/graph stages |
| 14 | AWS: bronze_seed_silver_gold | late-data | full data pipeline run |
| 15 | Snowflake: standalone gold-refresh | late-data | data refresh + verify |
| 16 | MDM + graph: connectivity/migrate/sync/verify | late-data | entity resolution over real data |
| 17 | MDM + graph: AWS E2E/status checks | late-data | verification over real data |
| 18 | Data: bounded smoke only | late-data | bounded data command |

Three stages need an explicit call, not just my guess:

- **Stage 7** (native-pull foundation): provision or deploy? It creates
  live Snowflake schema/pipe/task objects, which leans deploy, but nothing
  in it touches actual row data — it's schema, not application logic.
- **Stage 11** (loader role ownership): its own comment says it "must run
  after this stage's own dbt gold prerequisite... and before any
  gold-refresh" — it's sandwiched between two deploy-phase-adjacent
  concerns. Does it belong in deploy (grouped with stage 10, its
  prerequisite) or does its access-control nature make it provision?
- **Stage 13** (Postgres/graph prerequisites): it provisions infrastructure
  (an MDM Postgres instance is a real resource, not schema/config) but
  every stage that actually *uses* it (16, 17) is late-data. Does it stay
  in provision (matching what it structurally does) or move to sit closer
  to the late-data stages that depend on it?

## Recommendation

- Stage 7 → **provision**. Reasoning: distinguishing "provision" from
  "deploy" by whether the stage creates schema/infrastructure objects vs.
  application-level artifacts (dbt models, ECS task defs, Streamlit code)
  keeps the split legible; stage 7 creates schema/pipe/task
  infrastructure, not application logic.
- Stage 11 → **deploy**, immediately following stage 10 within the phase
  (stable partition preserves 10 < 11 automatically since both stay in the
  same phase). Its dependency on stage 10's output makes deploy the
  natural grouping regardless of its access-control flavor.
- Stage 13 → **provision**. It creates a real infrastructure resource (a
  Snowflake Postgres instance), matching provision's definition above; its
  *consumers* being in late-data doesn't change what stage 13 itself does.
  Ticket 02 will verify this placement doesn't strand a dependency.

## Answer

All three ambiguous stages resolved to the recommended classification.
Final assignment:

- **Provision**: 1 (Terraform state bucket), 2 (Neo4j Native App install),
  3 (passive infrastructure), 4 (access roles/policies), 7 (native-pull
  foundation), 13 (Postgres/graph prerequisites)
- **Deploy**: 5 (ECR image publish), 6 (ECS task defs/Step Functions), 9
  (MDM export targets), 10 (dbt gold), 11 (loader role ownership,
  immediately after 10 within the phase), 12 (Streamlit dashboard)
- **Early-data**: 8 (seed-universe)
- **Late-data**: 14 (bronze_seed_silver_gold), 15 (standalone
  gold-refresh), 16 (MDM+graph connectivity/migrate/sync/verify), 17
  (MDM+graph AWS E2E/status checks), 18 (bounded smoke)

Stable partition (original relative order preserved within each phase)
happens to already be monotonic within every phase bucket above — no
stage needs reordering *relative to its own phase-mates*. The resulting
full physical order is:

```
1, 2, 3, 4, 7, 13,   5, 6, 9, 10, 11, 12,   8,   14, 15, 16, 17, 18
└── provision ────┘  └──── deploy ─────┘  early  └──── late-data ────┘
                                            -data
```

Concretely, this moves: Stage 7 (native-pull foundation) and Stage 13
(Postgres/graph prereqs) earlier, ahead of Stages 5-6 and 9-12; Stages 5-6
(ECR publish, ECS task defs) later, behind 7 and 13; and Stage 8
(seed-universe) much later, from position 8 to immediately before
late-data (position 13 of 18 in the new order) — this last move is
exactly the case Ticket 02 must verify is safe (the dbt-gold-vs-empty-source
risk).

Ticket 02 is now unblocked — it should check every pair whose order
flipped, with the Stage 7↔5/6 and Stage 13↔5/6/9/10/11/12 pairs (newly
surfaced by this exact ordering) added to its known-candidate list
alongside the already-flagged Stage 8 vs. Stage 10 pair.
