# MDM and analytical silver: decision discussion

Status: interview in progress. No runtime change is authorized by this file.
Evidence: [repository assessment](research/2026-09-26-repository-assessment.md)
and [primary-source research](research/2026-09-26-primary-sources.md).

## Decision checklist

- [x] Q1: independent consumer progress — operator accepted the recommendation;
  structured reply verified 2026-09-26 10:34 ET.
- [x] Q2: shared parsing and separate mappings — operator accepted the
  recommendation; structured reply verified 2026-09-26 10:35 ET.
- [x] Q3: preserve all structured source fields and repeating groups — operator
  accepted the recommendation; structured reply verified 2026-09-26 10:37 ET.
- [ ] Boundary of consumer-specific transformations and irregular source formats.
- [ ] Version changes, replay and retained input scope.
- [ ] Q4: parsed-evidence retention and protection of lagging consumers/pinned runs.
- [ ] Correction/investigation requirements under the existing raw-retention policies.
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

## Q2: the shared reading boundary — accepted

Parse verified source bytes once per pinned reader/version into
a durable source-evidence publication, then apply independent MDM and analytical
mappings. Preserve source facts and provenance before either consumer's business
filtering, matching or field selection. This avoids duplicate decoding on routine
consumer retries but adds stored derived evidence and a common dependency.

Independent raw parsing remains a source-specific exception when the consumers'
needs cannot fit the shared records. Sharing parser code alone would still
permit duplicate processing executions and does not meet the selected default.

Fidelity is resolved for structured fields by Q3. Retention, publication/version
semantics and measured cost are unresolved.
The existing Source Contract's silver-to-Dataset Contract mapping is not silently
redefined; changes to it require the completed decision/spec discussion.

## Q3: evidence fidelity — accepted

For structured source files (JSON, CSV and XML), preserve all source fields and
repeating groups, including fields neither consumer uses today, with source names and
presence/repetition distinctions. MDM and analytics each select and transform what
they use. This reduces raw reparsing when a mapping needs a previously unused
field, at the cost of larger stored records. Exact raw bytes remain under the
existing source retention contract. This does not promise a generic extractor
can discover every fact in irregular HTML or PDF documents.

## Q4: parsed-evidence retention — pending

Recommendation: treat parsed publications as rebuildable derived evidence, not
another permanent history store. Keep current publications and any older version
required by unfinished consumers, active contract versions or pinned runs.
Delete superseded parsed versions only after those pins are released and required
replay can still be satisfied under the source's accepted raw-retention contract.

This does not change bronze/archive retention or copy historical assertions back
into the MDM journal. If source bytes are unavailable, do not claim regeneration;
either retain the required parse or state that replay is unavailable under the
accepted retention policy. Physical storage format, cleanup bounds and lag alerts
remain engineering/specification work.
