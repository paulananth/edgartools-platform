# 08 — Targeted prod lifecycle apply

**What to build:** After the prefix tests are green, an operator using the AWS admin prod profile plans only the warehouse lifecycle resource, aborts if the plan shows extra warehouse-bucket changes, applies that resource, and reads live lifecycle back: staging prefix 3/3, identity-refresh 7/7, Canonical Silver noncurrent-only 7 with no current expire.

**Blocked by:** 07 — Seal lifecycle prefixes and prove Joined Live Keys

**Status:** resolved

- [x] Plan is targeted at the warehouse lifecycle resource only (not the full prod root)
- [x] Apply aborts and reports if the plan mutates other warehouse-bucket resources
- [x] Live `get-bucket-lifecycle-configuration` shows the three trailing-slash prefixes and day counts from the spec
- [x] Canonical Silver still has no current-object expiration

Evidence: [08-targeted-prod-lifecycle-apply.md](../research/08-targeted-prod-lifecycle-apply.md)
