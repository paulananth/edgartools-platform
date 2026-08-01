# Implement Bounded ECR Retention with Rollback Safety

Type: task
Status: open
Blocked by: 04

## Question

How should deployment, cleanup, and ECR lifecycle configuration implement the
confirmed Rollback Image Set: current production, two verified successful
rollback images, and every digest referenced by a running ECS task?

Add explicit protected tags or registry state, retire stale task definitions as
required by the researched contract, preview lifecycle/cleanup candidates, and
refuse deletion when ECS or rollback reconciliation is incomplete. Cover the
warehouse and MDM repositories consistently without touching dependency images
that follow a different retention contract.
