# What is running in AWS

Read-only procedure for answering what is running and what remains billable.
Use the account map in [SKILL.md](SKILL.md); all times in the answer are ET.

## Confirm account and coverage

```bash
aws sts get-caller-identity --query Account --output text
aws ec2 describe-regions --region us-east-1 --query 'Regions[].RegionName' --output json
```

Match the account to the skill's active account before proceeding. Check each
returned region, assigning its name to `region` for the commands below. Use
bounded parallel reads when available. Keep AWS CLI pagination enabled. Record
failed calls as unknown coverage with their errors; an access denial is not an
empty inventory. If the operator limits the check to a region, state that scope.

## Inventory compute and automation

Run in every region:

```bash
aws ec2 describe-instances --region "$region" --filters Name=instance-state-name,Values=pending,running,stopping --query 'Reservations[].Instances[].{Id:InstanceId,Type:InstanceType,State:State.Name}' --output json
aws ecs list-clusters --region "$region" --query clusterArns --output json
aws rds describe-db-instances --region "$region" --query 'DBInstances[].{Name:DBInstanceIdentifier,Class:DBInstanceClass,Status:DBInstanceStatus}' --output json
aws rds describe-db-clusters --region "$region" --query 'DBClusters[].{Name:DBClusterIdentifier,Engine:Engine,Status:Status}' --output json
aws lambda list-functions --region "$region" --query 'Functions[].FunctionName' --output json
aws stepfunctions list-state-machines --region "$region" --query 'stateMachines[].{Name:name,Arn:stateMachineArn,Type:type}' --output json
aws scheduler list-schedules --region "$region" --query 'Schedules[].{Name:Name,State:State,Group:GroupName}' --output json
aws events list-rules --region "$region" --query 'Rules[].{Name:Name,State:State,Schedule:ScheduleExpression,ManagedBy:ManagedBy}' --output json
aws batch describe-job-queues --region "$region" --query 'jobQueues[].{Name:jobQueueName,Arn:jobQueueArn,State:state}' --output json
```

For each ECS cluster, assign its discovered ARN to `cluster`:

```bash
aws ecs describe-clusters --region "$region" --clusters "$cluster" --query 'clusters[].{Name:clusterName,Status:status,RunningTasks:runningTasksCount,PendingTasks:pendingTasksCount,Services:activeServicesCount,Instances:registeredContainerInstancesCount}' --output json
aws ecs list-tasks --region "$region" --cluster "$cluster" --desired-status RUNNING --query taskArns --output json
```

An `ACTIVE` cluster can be idle. Report running and pending task counts and
service counts. If tasks exist, use `describe-tasks` with a projection of task
ARN, status, task definition and start time; inspect each service's desired,
running and pending counts with `list-services` and `describe-services`.

For each Standard state machine, assign its discovered ARN to `machine`:

```bash
aws stepfunctions list-executions --region "$region" --state-machine-arn "$machine" --status-filter RUNNING --query 'executions[].{Name:name,Start:startDate}' --output json
```

Express workflows do not support `list-executions`; use their configured logs
and CloudWatch metrics for a stated observation window and report that limit.
For every Batch queue, use `list-jobs` for `RUNNING`, `STARTING`, `RUNNABLE`,
`PENDING` and `SUBMITTED` separately, distinguishing running from queued work.
An enabled queue alone establishes neither.

Lambda function presence establishes deployment, not an active invocation.
When functions exist, check CloudWatch invocation and concurrency metrics for
a stated recent window, and identify configured triggers. Describe an enabled
Scheduler schedule to obtain its expression and timezone. For an enabled
EventBridge rule, distinguish a scheduled rule (`ScheduleExpression`) from
an event-triggered rule; inspect projected target identifiers when necessary.
Step Functions-managed event rules support workflow integration and do not by
themselves establish a scheduled load. Rules on custom event buses require
`list-event-buses` followed by `list-rules --event-bus-name` for each bus.

## Inventory retained resources

List S3 buckets once for the account. Check ECR repositories and secret counts
in each region, projecting names or counts only:

```bash
aws s3api list-buckets --query 'Buckets[].Name' --output json
aws ecr describe-repositories --region "$region" --query 'repositories[].repositoryName' --output json
aws secretsmanager list-secrets --region "$region" --query 'length(SecretList)' --output json
```

Sum secret counts across paginated responses if the CLI returns separate page
counts. These resources can incur charges while compute is idle. Other retained
resources, such as EBS volumes, snapshots, public IPv4 addresses, NAT gateways
and logs, can also be billable; inspect them when the question includes a full
cost inventory. Use Cost Explorer to attribute reported charges, with its
reporting delay, rather than infer a dollar amount from resource counts.

## Report

Give the observation time in ET, account and region coverage, running and queued
work, enabled schedules, and retained resources separately. Name gaps and
service coverage: these checks cover EC2, ECS, RDS, Lambda, Step Functions and
Batch, not every AWS compute service. Use counts from live reads; keep dated
snapshots in operational records rather than in this procedure. A running-work
check authorizes reads only; stopping, deleting or disabling resources is a
separate action.
