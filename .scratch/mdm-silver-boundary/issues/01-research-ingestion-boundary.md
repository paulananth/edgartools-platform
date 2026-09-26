# Research the MDM and analytical silver boundary

Type: research
Status: research complete; architecture decision pending
Base: `origin/main` at `2b52b2913d12679df3651bc5cd3e05b125abc403`
Branch: `codex/mdm-silver-boundary-research`

Operator question: must MDM and silver be decoupled for flexibility, and does
that require processing files twice with different configuration?

## Checklist

- [x] Protect other work and create a dedicated branch/worktree — live Git
  status, worktree and PR inspection; 2026-09-26 07:25 ET.
- [x] Route through ask-matt and delegate primary-source research using research
  skill — skill files read and scoped background task launched; 2026-09-26 07:25 ET.
- [x] Verify the present boundary and Source Contract design against current
  source code and git history — [repository assessment](../research/2026-09-26-repository-assessment.md);
  2026-09-26 07:29 ET.
- [x] Review and retain the cited primary-source findings — background report
  read, AWS/Ataccama/dbt pages rechecked; 2026-09-26 07:29 ET.
- [x] Verify note links and distinguish observations from proposals and measured
  results — three notes, eleven local links and whitespace validated;
  2026-09-26 07:29 ET.
- [x] Prepare the comparison and recommendation; present the first decision
  question — independent consumer progress asked through structured user input;
  2026-09-26 07:29 ET.

## Decision frontier

Q1 accepted: MDM continues from verified evidence when analytical silver
publication fails or lags, and vice versa. Each has its own progress/retries,
while a combined output waits for every required consumer. Operator's structured
reply verified 2026-09-26 10:34 ET. This does not claim a cross-system atomic
transaction or weaken MDM's own atomic master/journal/checkpoint commit.

Q2 next: choose shared durable source evidence with independent consumer mappings,
or independently read/parse bronze for each consumer. Recommendation: shared
source evidence; its fidelity, retention and version contracts remain later gates.

Later questions depend on Q2: retention and replay horizon, contract/version
ownership, and the bounded migration trial. Only Q1 is accepted so far.

Research completion does not accept or implement an architecture. The interview,
ADR/spec, migration tickets and cost/fidelity prototype are follow-up work after
the decision discussion; they are not silently authorized by a research request.
