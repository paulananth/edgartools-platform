# v2 Mongo Decision Projection — implementation

Parent: `.scratch/mongodb-v2-agent-interface/map.md`
Contract: `.scratch/mongodb-v2-agent-interface/data-contract.md`
ADR: `docs/adr/0009-mongo-decision-projection.md`

Snowflake stays v1 Agent System of Engagement. This work implements the
separate READY-after publisher that writes Atlas documents matching the
accepted data contract. Ticket 1 uses a mocked store only.
