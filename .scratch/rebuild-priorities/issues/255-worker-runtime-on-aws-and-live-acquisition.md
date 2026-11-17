# 255: The worker runtime on AWS and the live acquisition that waits for it

Priority: 255. Map: [Rebuild priorities](../map.md). Opened 2026-11-17 (operator: "Move AWS to a separate ticket and delete it here"). Moved out of ticket 212, which held these as the parts of ticket 71 ("The configured worker runtime on AWS (Step Functions and task definitions)").

Type: task. Status: open (waits for the operator's AWS destinations). Blocked by: the operator naming the AWS destinations, stores and roles. Related: [71](71-mastering-to-done-24-worker-runtime-on-aws.md), [229](229-live-acquisition-waits-for-the-worker-runtime.md).

## Question

What does it take to run the configured pipelines on AWS (Step Functions, task definitions, live acquisition), and in what order? Nothing here starts without the operator's word on AWS: the loads run locally and in the hosted Snowflake Postgres store today, and a provider capture runs on the machine by the unit.

## Parts

- [ ] The operator names the AWS destinations, stores and roles (Codex's go-live review, items 2 and 4): where consumers are delivered, which PostgreSQL hosts each store, the worker and verifier logins
- [ ] Design: one state machine shape for any target (submit, per step: work and verify until verified, finalize), its timeouts and retries; GoF consult
- [ ] Task definitions for the worker and verifier images; the image build (needs a container runtime)
- [ ] install.sh deploy stages for them; tests; review; PR; deploy only on the operator's word
- [ ] Source activation of SEC Company and GLEIF for live acquisition (the local switch-on over captured files is done: SEC Company by ticket 114; from ticket 02; operator, 2026-10-14: "Move to ticket 71 (Recommended)"): an acquisition proof from a real acquisiti...
- [ ] Source activation of `sec.submissions.person` (from ticket 11): the same acquisition proof
- [ ] `rules run --target mdm` end to end (from ticket 02)
- [ ] The live SEC Company qualification (from ticket 03, L8; parked by the operator until AWS: `.planning/workstreams/sec-company-live-qualification-20261013/TICKET.md`)
- [ ] Live acquisition through `provider.capture` runs on the worker runtime on AWS (it runs on the machine today, one unit at a time under the shared provider lease, and is qualified offline; moved from ticket 229)
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
