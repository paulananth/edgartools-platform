# 19 — Complete the filing-to-Silver acceptance seam

**What to build:** Carry a discovered filing candidate from its authorized
Fetch Decision through verified Bronze evidence and Logical Source Revision to
a verified Silver publication or an explicit terminal non-publication outcome.

**Blocked by:** 05 — Decide silver delta publication and scope-completion
semantics; 18 — Materialize ordered logical source revisions

**Status:** ready-for-agent

- [ ] Expected Silver producers, tables, and scopes are sealed before processing
  and each records a verified publication or explicit no-impact outcome.
- [ ] Success requires read-back verification of authoritative Silver state;
  parser success, landing upload, workflow success, or load-command success is
  insufficient by itself.
- [ ] Source Change Status joins decision, capture, revision, processing,
  expected-producer progress, blocker, and next action for the candidate.
- [ ] A Silver failure leaves prior Silver authoritative and blocks only later
  revisions for the same logical key.
- [ ] The acceptance test asserts durable external evidence rather than
  concrete Facade, Strategy, or handler implementation classes.
