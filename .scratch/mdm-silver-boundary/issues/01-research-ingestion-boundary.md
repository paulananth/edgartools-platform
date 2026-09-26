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

Q2 accepted: shared durable source evidence with independent consumer mappings;
separate raw parsing is a source-specific exception when the shared records cannot
serve the source's needs. Operator's structured reply verified 2026-09-26 10:35 ET.

Q3 accepted: preserve all structured source fields and repeating groups, including
currently unused fields. Operator's structured reply verified 2026-09-26 10:37 ET.

Q4 accepted: keep current and needed parsed versions; prune superseded versions
only after consumer/run pins clear and required replay remains possible under
existing source-retention contracts. Operator's reply verified 2026-09-26 10:48 ET.

Q5 accepted: independently version reading and consumer mappings, so a mapping-only
change reruns the affected consumer from retained parsed evidence. Raw reparsing
follows reader changes, not unrelated mapping changes. Reply verified
2026-09-26 10:49 ET.

Q6 next: bounded SEC Company + GLEIF proof before broader migration; preserve the
existing outputs until correctness, recovery, selective replay and measured cost
are qualified. Recommendation: yes.

Consumer-specific transformations follow Q2–Q3; irregular formats retain the
existing source-specific exception. Q1–Q5 are accepted. After Q6, present the
complete decision package for confirmation and finalize the ADR/spec.

Research completion does not accept or implement an architecture. The interview,
ADR/spec, migration tickets and cost/fidelity prototype are follow-up work after
the decision discussion; they are not silently authorized by a research request.
