# Data engineer requirements

Decided from [the runtime account](../../docs/research/claude-codex-runtimes-2026-10-06.md), [data-platform](../data-platform/SKILL.md), [bookkeeping](../bookkeeping/SKILL.md), and [change-journal](../change-journal/SKILL.md). This note is the boundary. The skill that follows it does not add a second one.

## Scope

The data engineer moves captured files through workers and commands that already exist.

In scope:

- A feed that already has rules, or a handoff from data-onboarding once those rules exist.
- Checking that the feed binding and each worker profile resolve, then running the declared steps in the order [data-platform](../data-platform/SKILL.md) gives: read, combine when the pipeline declares it, prepare, merge, publish.
- Inspecting a run and resuming it. Bookkeeping owns the control commands. The Change Journal owns delivery recovery. This skill does not restate either procedure.
- Saying when a step has no worker. That is unfinished implementation. It is not a reason to run the step another way.

Out of scope: deciding a class, a kind, or an identifier (data-modeling); profiling files (data-profiling); writing the first contract or a live rule change (data-onboarding, refining-rules); approving or switching a version on; editing `crates/source-contract`, `skills/data-platform/READING.md`, or `skills/data-platform/COMBINING.md`.

## Use when

Use when the operator wants captured files read, combined, prepared, merged, or published with the existing workers, or wants a run inspected or resumed.

Do not use it to decide what a part is, to measure what the data shows, or to approve a rules version.

## Refusals

- Do not approve a version or switch one on. Data-onboarding's [APPROVE.md](../data-onboarding/APPROVE.md) owns that, and the operator decides.
- Do not invent a command, a worker profile, or a flag.
- Do not request anything from `sec.gov`, and do not read or print a secret. The variables are the ones data-platform and bookkeeping already name.
- Do not run a profile that `workers describe` does not resolve.
- Do not treat a qualification note in [READING.md](../data-platform/READING.md) as permission to retire a reader or activate a source version.
- Do not edit Claude-owned or Codex-owned paths, including open PR #834 (`codex/configured-xml-framing-20261006`).
- Do not start a silver load or an RDM load. Neither writer exists.

## Open questions

1. Company catalog joins, census joins, pagination, classification, provenance, and full Company mastering are still unqualified in [READING.md](../data-platform/READING.md). Run only a profile `workers describe` resolves. Report the rest as unfinished. Do not decide that a partial read is full mastering.
2. Active GLEIF archive and XML retirement is unfinished on `main`. PR #834 is the open Codex branch for bounded XML framing. Leave it untouched, and do not activate that source.
3. Data-onboarding's missing-command table says the general silver writer is not built. There is no command to add here.
4. [The RDM spec](../../docs/specs/rdm/spec.md) is a draft and no command writes a code set. Publishing reference data is not this skill's job.
