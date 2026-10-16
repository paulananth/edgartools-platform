# Agent-driven local test environments

Use this policy for persistent local testing and Proving Runs across MDM,
RDM, silver, Rules, Bookkeeping and Change Journal on PostgreSQL 16.

**Status:** the policy is agreed; the environment lifecycle automation is
pending the local-agent-stores implementation. This file adds no executable
command. Until the implementation exists, report that gap rather than claim
an environment or verification is complete.

## Automatic baseline promotion

The operator selected automatic promotion on 2026-10-16: agents build and
verify a candidate, then make it the default for future environments when
every gate below passes. Do not ask for another approval of that local test
baseline. A baseline is a versioned test starting point, not approval of a
Source Contract, matching rule or production activation.

1. **Pin the candidate.** Give it an immutable identity and record the code
   revision, PostgreSQL image, migration checksums, rule versions, input
   receipts and fixture hashes. The initial program is Company first, using
   approved local captures plus invented edge-case fixtures. Existing source
   and rule approvals retain their recorded meaning.
2. **Verify all six stores.** A verifier checks real migrations and restricted
   roles, expected contents, provenance, required links and idempotent replay.
   Source numbers stay exact, following the project's BIGINT/64-bit rule;
   unresolved representability blocks promotion rather than rounding a value.
3. **Prove recovery.** Quiesce workers and capture a consistent baseline across
   the six stores and its artifacts. Restore into a separate owned environment
   and compare business contents and lineage. Retain the MDM identity registry
   and accepted decisions: source-only reconstruction does not prove identical
   published IDs. Verify recovery without inherited live leases or unintended
   worker execution.
4. **Bind the evidence.** Verification refers to the exact immutable candidate;
   the builder's success message is not read-back proof. Changed inputs, code,
   migrations or rules require qualification of the resulting candidate.
5. **Promote atomically.** Move the default-baseline reference only if its
   predecessor still matches the one the candidate was qualified against. A
   superseded candidate must be requalified; it cannot overwrite a newer
   default. Record the candidate, predecessor and verification evidence.
6. **Keep environments pinned.** Promotion affects new environments. Existing
   agent environments retain their selected baseline and working state; a
   promotion never resets or migrates them implicitly.
7. **Retain recovery evidence.** Keep the prior baseline and verified backups.
   A failed or incomplete check leaves the default unchanged and records the
   reason. If a promoted baseline later fails qualification, restore the default
   reference to a previously verified baseline and retain the failed version
   for diagnosis; existing environments remain pinned.

These gates belong in executable environment code and behavior tests. The
skill tells agents what to do; prose and agent judgment alone do not enforce
promotion. Publish counts and invented examples only; keep capture contents,
credentials and connection addresses out of public artifacts and chat.
