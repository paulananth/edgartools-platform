# Design the Cost-Audit Contract and Test Seams

Type: task
Status: resolved
Blocked by: 01, 06, 07

## Question

What command interface, normalized evidence model, finding schema, ranking
policy, graceful-degradation rules, and injected AWS-query seams let the audit
remain deterministic, testable, read-only, and useful both to humans and CI?

The design must reuse appropriate existing cost and S3 audit behavior without
coupling analysis to shell output or forcing a design pattern.

## Answer

Resolved 2026-09-02. The mandatory GoF review found no demonstrated reason to
refactor the existing `aws-cost.sh` or `aws-storage-audit.sh`: each has changed
only once, so a Strategy, Template Method, or class hierarchy would add
indirection without reducing current change cost.

Accepted public TDD seams:

1. The CLI consumes either live AWS metadata or a versioned evidence snapshot
   and renders a stable JSON/Markdown report. Fixed snapshots make threshold,
   ranking, delay, redaction, and degradation behavior deterministic.
2. All live AWS calls pass through one injected command boundary with a strict
   read-only `(service, operation)` allowlist. Tests prove disallowed mutation
   verbs cannot execute.
3. S3 retention uses canonical Accession Authority rows, a deterministic plan
   hash, exact VersionIds, and independent plan/apply validation. The apply
   command re-lists each full accession prefix and proves post-delete absence.

The implementation remains a small Python operations script, not a pattern
hierarchy: typed snapshot/report values, pure analysis/rendering functions, one
read-only AWS CLI adapter, and one narrowly scoped exact-VersionId S3 delete
adapter. Year-based source deletion uses an explicit Accession Retention
Authority and complete-bundle selection; it never infers a form policy from an
accession year alone.
