# 24: The configured worker runtime on AWS (Step Functions and task definitions)

Priority: 71, tier 5, needs SEC requests or AWS. Map: [Rebuild priorities](../map.md). Moved from `.scratch/mastering-to-done/issues/24-worker-runtime-on-aws.md` on 2026-10-13 after #953 merged.

Status: open, waits for the operator's AWS destinations. Raised by the operator, 2026-10-13 ("update ... step functions"); split from ticket 23 the same day ("README + install.sh now (Recommended)").

## Question

The old pipeline's ECS task definitions and Step Functions were retired with its commands (#766). The configured platform runs a source's target as Bookkeeping work: a run is submitted (`rules run`), each step's workers claim, work and report, and separate verifiers admit (`edgar-warehouse workers work|verify <profile> <run>`). On AWS that needs, for each target (Company and Person `mastering`, GLEIF `mdm`, the publish pipeline), a state machine that submits the run and loops the workers and verifiers of each step until every unit is verified, then finalizes; and task definitions for the worker and verifier logins.

## Checklist

- [ ] The operator names the AWS destinations, stores and roles (Codex's go-live review, items 2 and 4): where consumers are delivered, which PostgreSQL hosts each store, the worker and verifier logins
- [ ] Design: one state machine shape for any target (submit, per step: work and verify until verified, finalize), its timeouts and retries; GoF consult
- [ ] Task definitions for the worker and verifier images; the image build (needs a container runtime)
- [ ] install.sh deploy stages for them; tests; review; PR; deploy only on the operator's word

## Moved here (2026-10-14)

- [ ] Source activation of SEC Company and GLEIF (from ticket 02; operator, 2026-10-14: "Move to ticket 71 (Recommended)"): an acquisition proof from a real acquisition run (manifest, producer counts, checks); GLEIF's `source.yaml` declares an `acquisition` first
- [ ] `rules run --target mdm` end to end (from ticket 02)
- [ ] The live SEC Company qualification (from ticket 03, L8; parked by the operator until AWS: `.planning/workstreams/sec-company-live-qualification-20261013/TICKET.md`)
