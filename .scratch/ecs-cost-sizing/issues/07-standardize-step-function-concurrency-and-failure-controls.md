# Standardize Step Functions Concurrency and Failure Controls

Type: grilling
Status: open
Blocked by: 05, 06

## Question

What common contract should production state machines use for Map
`MaxConcurrency`, ECS retry intervals/attempts, timeouts, tolerated failure,
and validation-failure handling? Compare the live workflow families, including
the `bronze-seed-silver-gold` Map concurrency of 20, strict candidate
concurrency of 2, and the residual-holds retry profile. Preserve workload-
specific exceptions only when backed by measured throughput, quota, conflict,
or correctness evidence.
