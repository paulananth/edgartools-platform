# Run the hosted load on AWS

Status: open
Type: task
Owner: claude (operator, 2026-11-27: "upload image and setup a large step machine to run the complete load after clearing the hosted postgress")

Operator, 2026-11-27, in order: "use only step function machine in aws"; the choice "Deploy it to AWS (Recommended)"
(the same state machine in AWS Step Functions, one ARM Fargate task as its worker, logins in Secrets Manager, Terraform
under `infra/`); "upload image and setup a large step machine to run the complete load after clearing the hosted
postgress"; "upload data from mac to aws bronze if needed do not download from sec without approval". These words are the
approval of the AWS cost (one 16 vCPU, 120 GB task, about 1 USD an hour while it runs) and of the clear.

Why: the finish's links write fails from a home uplink (about 0.25 to 0.4 MB/s to the hosted store, dropped after about
10 minutes inside one transaction). The same upload to the bronze bucket ran at about 6.5 MB/s.

## Checklist

- [x] Captures the load jobs file reads (17 folders) are in the bronze bucket under `load/`: 111,567 files, 6,978,944,437 bytes, none missing or of another size than on this Mac (2026-11-27 13:19 ET)
- [x] Terraform root `infra/terraform/load-machine` and `infra/load-pipeline/aws-load.sh`: `terraform validate`; the generated state machine equals the file with 11 lanes; the record keeper run in the AWS CLI image with a stand-in (a stop during a long copy starts the final copy at once; the time bound ends it) (2026-11-27 13:19 ET)
- [x] Apply and `--prepare`: image of commit 734f464c in ECR, 6 logins in Secrets Manager (names read back), state machine with 11 lanes, task of 16 vCPU, 120 GB, 200 GiB, no task started (2026-11-27 13:35 ET)
- [x] Trial on AWS, read only (`--plan ncen-fund`, run `aws-smoke-20261127`): the task fetched the captures in about 5 minutes, the worker polled, readiness ran and passed 11 of 12 checks, the execution failed on the twelfth and the task stopped (2026-11-27 13:35 ET)
- [ ] Snowflake compute for the mirror: `MIRRORED` fails because resource monitor `EDGARTOOLS_PROD_MONITOR` (monthly, 10 credits in Terraform) has exceeded its quota and every warehouse is refused, from AWS and from the Mac alike. The operator's to raise or wait out
- [ ] Clear the hosted stores: mirror suspended, backups of control and RDM, five stores truncated, RDM restored, mirror resumed and read back
- [ ] Readiness passes in the AWS task
- [ ] The complete load succeeds on AWS, the finish included
- [ ] Gold accepted: `dbt build` passes every link test
- [ ] `/code-review` (Standards, Spec, GoF), PR green and merged
- [ ] ~~The `/gof-refactor-reviewer` consult before production code~~ deferred to this ticket's GoF review axis: it was not run before writing
- [ ] Learning → skill
