# Prove Atomic Attempt Supersession

Type: task
Status: open
Blocked by: none
Blocks: 05, 07
Labels: wayfinder:task

## Question

Can an attempt superseded after the admission precheck still be prevented from
completing at the atomic database boundary under concurrent execution?

## Checklist

- [ ] Make the PostgreSQL integration proof runnable with the compiled
  `source_contract` extension; retain the current test's assertions.
- [ ] Exercise the race between admission precheck and database completion.
- [ ] Confirm stale attempts cannot complete or replace admitted evidence.
- [ ] Run the affected retry, concurrency, precision, flag/exception and
  historical receipt checks on the new implementation head.
- [ ] Record the exact command, result and remaining gaps.
- [ ] Learning → skill: record `none` or name the skill line changed.
