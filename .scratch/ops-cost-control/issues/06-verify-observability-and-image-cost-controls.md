# Verify Observability and Image Cost Controls

Type: task
Status: open
Blocked by: 02, 03, 05

## Question

Does an immutable-image production validation demonstrate lower CloudWatch
ingestion volume, seven-day retention without drift, bounded ECR growth, and a
rehearsed rollback to both protected images without losing forensic or release
evidence?

Compare log bytes/records and estimated ingestion/storage cost to the baseline,
verify required error/run fields, audit every ECR deletion candidate against
running tasks and the Rollback Image Set, and prove current plus both rollback
images remain pullable and launchable. Record any residual cost contributor as
new fog rather than broadening cleanup implicitly.
