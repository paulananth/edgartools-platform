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

- [ ] Captures the load jobs file reads (17 folders, about 6.75 GB) are in the bronze bucket under `load/`
- [ ] Terraform root `infra/terraform/load-machine` and `infra/load-pipeline/aws-load.sh`
- [ ] Apply and `--prepare`: image of `main`'s commit in ECR, logins in Secrets Manager, no task started
- [ ] Clear the hosted stores: mirror suspended, backups of control and RDM, five stores truncated, RDM restored, mirror resumed and read back
- [ ] Readiness passes in the AWS task
- [ ] The complete load succeeds on AWS, the finish included
- [ ] Gold accepted: `dbt build` passes every link test
- [ ] `/code-review` (Standards, Spec, GoF), PR green and merged
- [ ] ~~The `/gof-refactor-reviewer` consult before production code~~ deferred to this ticket's GoF review axis: it was not run before writing
- [ ] Learning → skill
