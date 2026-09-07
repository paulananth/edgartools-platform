# Recurring AWS Cost Optimization Audit Context

## Settled vocabulary

- **Cost Audit** — a pass that gathers billing and resource evidence, analyzes
  it, and renders findings. Only its separately invoked S3 retention apply
  operation has mutation capability.
- **Optimization Candidate** — an evidence-backed opportunity or drift signal
  that deserves operator review. It does not authorize a change.
- **Remediation** — any state-changing AWS operation, including delete, stop,
  resize, lifecycle, retention, schedule, concurrency, and IAM changes.
  Remediation appears only as inert guidance in the audit output; exact S3
  VersionId deletion exists only in the separate protected apply workflow.
- **Projected monthly savings** — a conservative USD estimate derived from a
  cited billed usage dimension or an explicitly labeled approximation.
- **Material candidate** — projected savings of at least USD 1/month.
- **Spend drift** — a service's most recent closed-month spend exceeds the
  preceding closed month by more than 20 percent. Partial-month totals do not
  trigger this finding.
- **Years in active scope** — the rolling business window in which a filing or
  derived artifact is consumed by a named product/workflow. For SEC source
  artifacts it becomes a deletion cutoff only through the Accession Retention
  Authority and complete-bundle checks below.
- **Accession Retention Authority** — a durable row binding accession, form,
  filing date, item/source classification, applicable consumer windows, and
  cross-accession references used to compute the maximum `retain_through`
  date. It is the deletion authority for every registered document/text object
  in that accession bundle.
- **Artifact Retention Class** — a bucket/prefix pattern plus artifact type,
  date basis, minimum retention period, terminal disposition, and required
  protection checks.
- **Derived Filing Text** — a rebuildable normalized-text projection identified
  by filing accession and interpretation version and produced from retained
  Bronze filing evidence. It is not source evidence.
- **Retirable Derived Filing Text** — a Derived Filing Text identity outside
  the authoritative required set that has satisfied its deletion-eligibility
  boundary. This status never applies to the underlying Bronze evidence.
- **Safety finding** — missing or conflicting evidence that could make a
  remediation unsafe. Safety findings are always reported, even below the
  monetary threshold.

## Settled operating contract

- Manual and weekly GitHub Actions execution use the same command.
- AWS identity is checked against an explicit expected account before resource
  evidence is accepted.
- Collection degrades explicitly when an IAM permission or optional data source
  is unavailable; missing evidence must never be converted into a zero-cost or
  safe-to-delete conclusion.
- S3 and ECS/Fargate findings rank before secondary-service findings at equal
  severity.
- Existing ECS canary and ECR rollback gates remain the authority for whether
  a candidate can be remediated.
- Promotional credits and Free Tier affect payment, not whether usage is an
  optimization candidate.
- An S3 deletion candidate must identify the exact retention class, date basis,
  accession authority, complete expected bundle, and VersionIds. Unmatched
  objects degrade to `insufficient_evidence` until they can be classified.
- Derived filing-text deletion authority is exact-accession/version scoped. It
  requires two consecutive complete successful sweep manifests spanning at
  least 30 days, a hash-bound exact-VersionId plan, verified Silver retirement
  before deletion, and durable post-delete evidence. It cannot authorize a
  Bronze deletion.

## Explicit non-goals

- No non-S3 auto-remediation mode or hidden mutation flag.
- No organization-wide rightsizing recommendation based only on aggregate
  Cost Explorer totals.
- No paid telemetry service enabled merely to make this audit more detailed.
