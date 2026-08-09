# Build Workflow Unit Economics

Type: research
Status: open
Blocked by: 02, 11, 12

## Question

How quickly does each production workflow produce a complete validated output,
what does it cost per successful execution, per 1,000 committed records, and
per 1,000 exported records, and what useful output or operator capability does
that time and spend purchase?

Attribute Fargate vCPU-seconds and GB-seconds by stage and profile, Step
Functions state transitions and Map Runs, retries and duplicate work, and
material logging or storage overhead. Report end-to-end and stage duration,
critical-path wait, records per second, failure rate, freshness contribution,
and output completeness beside cost. Build the cost-versus-completion-time
frontier so faster valid configurations are visible even when they cost more.
Separate fixed orchestration cost from record-volume-dependent work, and mark
workflows whose record-based denominator is not meaningful, such as
connectivity or verification utilities.
