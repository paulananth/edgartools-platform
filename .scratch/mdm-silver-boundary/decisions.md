# MDM and analytical silver: decision discussion

Status: interview in progress. No runtime change is authorized by this file.
Evidence: [repository assessment](research/2026-09-26-repository-assessment.md)
and [primary-source research](research/2026-09-26-primary-sources.md).

## Decision checklist

- [x] Q1: independent consumer progress — operator accepted the recommendation;
  structured reply verified 2026-09-26 10:34 ET.
- [ ] Q2: shared source evidence or separate raw parsing.
- [ ] Evidence fidelity and the boundary of consumer-specific transformations.
- [ ] Version changes, replay and retained input scope.
- [ ] Retention, lagging consumers and correction/investigation requirements.
- [ ] Migration proof and implementation scope.
- [ ] Confirm shared understanding and write the final ADR/spec.

## Q1: independent progress — accepted

MDM may load/master verified source evidence while analytical silver publication
is delayed or fails. Analytical silver may progress while MDM fails or holds
records. Each consumer has its own durable progress and retries. A combined
output is ready only when its required consumer coverage is complete and the
input versions/watermarks are compatible.

This separates consumer completion; it does not loosen MDM's transaction
boundary for master changes, journal evidence, checkpoints and publication intent.
A shared parser, if selected in Q2, remains a prerequisite for both consumers
for the affected artifact.

## Q2: the shared reading boundary — pending

Recommendation: parse verified source bytes once per pinned reader/version into
a durable source-evidence publication, then apply independent MDM and analytical
mappings. Preserve source facts and provenance before either consumer's business
filtering, matching or field selection. This avoids duplicate decoding on routine
consumer retries but adds stored derived evidence and a common dependency.

The alternative is independent bronze-to-MDM and bronze-to-silver reads/parses;
sharing parser code alone still permits duplicate processing executions.

Fidelity, retention, publication/version semantics and measured cost are unresolved.
The existing Source Contract's silver-to-Dataset Contract mapping is not silently
redefined; changes to it require the completed decision/spec discussion.
