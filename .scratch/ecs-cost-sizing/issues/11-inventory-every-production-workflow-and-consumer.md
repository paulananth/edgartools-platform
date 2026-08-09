# Inventory Every Production Workflow and Consumer

Type: research
Status: open
Blocked by: 01

## Question

For every live `edgartools-prod-*` Step Functions state machine, what triggers
it, which ECS commands and task-definition revisions does it invoke, which
outputs or integrity claims does it produce, who or what consumes those
outputs, how often is it executed, and what are its recent success, failure,
retry, and duration distributions?

Identify overlapping wrappers, duplicate MDM chains, one-off repair workflows,
operator utilities, scheduled production paths, and workflows with no observed
execution or downstream consumer. Bind the inventory to the post-Claude state
machine definition, immutable image digests, execution-history window, and
output evidence. Surface facts only; keep, merge, and retirement decisions
belong to the workflow-portfolio ticket.
