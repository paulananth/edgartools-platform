# Roadmap: fix-pipelines — v1.0 Pipeline Observability

**Status:** COMPLETE — shipped 2026-05-16
**Archive:** [v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)

All 4 phases shipped: Failure Surfacing (Phase 1) · Status Completeness (Phase 2) ·
Failure Notifications (Phase 3) · SEC Rate Limiting (Phase 4)

Milestone goal achieved: pipeline failures surface as hard Step Functions FAILED states,
`status.sh` covers all 5 state machines with stage-level detail, operators receive SNS
email within 60 seconds of any failure, and all SEC EDGAR calls are rate-limited to
9 req/sec per ECS task.
