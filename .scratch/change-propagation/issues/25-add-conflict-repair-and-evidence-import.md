# 25 — Add conflict, repair, exclusion, and evidence-import workflows

**What to build:** Give operators safe, auditable workflows for conflicting
immutable evidence, explicit exclusions, corrective child revisions, and
checksum-verified evidence imported from another environment or account.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable; 18 —
Materialize ordered logical source revisions

**Status:** ready-for-agent

- [ ] Different bytes under one immutable SEC identity are both retained and
  quarantined; neither arrival order nor a mutable latest pointer chooses one.
- [ ] A repair creates an immutable child revision naming accepted and rejected
  evidence, its operator authorization, and reason without rewriting history.
- [ ] An exclusion is authorized, reasoned, scoped, visible in Source Change
  Status, and cannot masquerade as a source deletion or no-impact result.
- [ ] Cross-environment evidence becomes processable only after explicit local
  authorization, checksum verification, and preserved source lineage.
- [ ] Database roles keep coordinator, acquisition worker, processor, Silver
  finalizer, and operator transition ownership separate.
