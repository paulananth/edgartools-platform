# Research the MDM and analytical silver boundary

Type: research
Status: complete — research and architecture direction accepted
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

## Architecture discussion checklist

- [x] Record six accepted decisions with the operator replies and verification
  times — [decision log](../decisions.md) checked; 2026-09-26 10:58 ET.
- [x] Rebase onto current main and refresh the historical countryCode example —
  `3ea3a6b1`, PRs #720/#721 verified; 2026-09-26 10:54 ET.
- [x] Write a concrete review package: architecture brief, proposed specification
  and proposed ADR — seven Markdown files and 27 local links validated,
  whitespace checked; 2026-09-26 10:58 ET.
- [x] Confirm the complete shared understanding and finalize decision-record
  status — Q7 operator reply verified; 2026-09-26 11:11 ET.

Engineering qualification and runtime implementation remain outside this
completed research. The proposed specification explicitly lists their gates.

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

Q6 accepted: bounded SEC Company + GLEIF proof before broader migration; preserve the
existing outputs until correctness, recovery, selective replay and measured cost
are qualified. Operator's structured reply verified 2026-09-26 10:54 ET.

Consumer-specific transformations follow Q2–Q3; irregular formats retain the
existing source-specific exception. Q1–Q6 are accepted. The concrete
[architecture brief](../architecture.md) and [architecture requirements](../specification.md)
are accepted through Q7, reply verified 2026-09-26 11:11 ET. The interview frontier
is closed. No implementation ticket or runtime change is claimed.

Research completion does not accept or implement an architecture. The interview,
ADR/spec, migration tickets and cost/fidelity prototype are follow-up work after
the decision discussion; they are not silently authorized by a research request.
