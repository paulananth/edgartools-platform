# Lock how the v2 publisher is tested

Type: grilling
Status: resolved
Blocked by: 06

## Question

How does the separate READY-after publisher get tests, now that writer
and data contract are locked?

CI in this repo has no Mongo today. M0 is a live operator cluster, not
a fixture we should assume in GitHub Actions. Options at minimum: mock
the driver in unit tests; Testcontainers Mongo in CI; live Atlas M0 in
CI.

## Comments

- 2026-09-11 Q1 accepted **A**: Unit tests mock the Mongo driver against
  the accepted data contract. Optional operator smoke on M0 later. No
  Atlas secrets in CI.

## Answer

Publisher tests are **unit tests with a mocked Mongo driver** that assert
READY-gate, in-place hide, and document shape against
[data-contract.md](../data-contract.md). Optional operator smoke on M0
after a cluster exists. No Atlas secrets, Testcontainers, or live M0 in
CI.
