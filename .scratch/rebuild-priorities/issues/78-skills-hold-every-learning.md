# Skills hold every learning

Priority: 78, tier 1, in flight (raised by the operator, 2026-10-14). Map: [Rebuild priorities](../map.md).

Type: task (documentation and one lint). Status: claimed (Claude, 2026-10-14 ET, branch `claude/skills-hold-learnings`). Blocked by: none.

## Why

Operator, 2026-10-14: "Review all the skills the goal is once we are done with this project all learning and best practices and how to must be abstracted to the skills".

The review (2026-10-14 17:10 ET) found the skills strong on taking a feed through the platform, and weak on two things the project learned:
- how to engineer the MDM store: Postgres rules and the Merge Stage's design, held only in `CLAUDE.md`;
- how to work in this repo: branches, reviews, tests, CI, and how to report to and ask the operator, held in `CLAUDE.md` and in Claude's private memory, which Codex and Grok never see.

Operator ruling on the split (2026-10-14, "Agreed"): no "workflow" skill. A skill is a method for a kind of work; how to work in this repo goes into `AGENTS.md` and `CLAUDE.md`, which every runtime reads; rules about data work go into the existing data skills; the MDM and Postgres engineering rules become one new skill, `mdm-engineering`.

## Checklist

- [x] New skill `skills/mdm-engineering/`: the hosted-Postgres target, lean design (remove a layer, no size refusals), the Merge Stage record by record, Postgres lookup and index rules, migrations, writes and transactions, choosing the cheapest proof; `link.sh`, agent file; in the genericity lint's scope; lint 62 pass, skill command tests 10 pass; PR 1 2026-10-14 17:12 ET
- [x] Data-work rules into the existing skills' hard stops: explain a digest in plain words; descriptive rule version names; approve, switch on and merge only on the operator's own words; findings, not process; counts only in a public repo; no request to a provider without permission. Already there: approve only on the operator's words, test before approval, no provider request, no secret, one question at a time, findings not process (onboarding's story section). Added to data-onboarding and refining-rules: plain words before a digest, descriptive version names, no data value in a public repo; data-platform's summary too. Merge on the operator's word is repo process (part 4) 2026-10-14 17:16 ET
- [x] This week's lessons into their skills:
  - [x] data-quality and refining-rules: a new quality version changes every record id, so tests that pin ids compare under the old version: data-quality **write**, refining-rules change-quality step 3 2026-10-14 17:16 ET
  - [x] data-quality: the run report checks (records, set aside, empty-value rate per field, newest record's age) and how to read them: data-quality **read** (onboarding's test step already reports them) 2026-10-14 17:16 ET
  - [x] data-onboarding switch-on: a source is activated only with an acquisition proof from a real acquisition run: APPROVE.md, "Switch on" 2026-10-14 17:16 ET
  - [x] data-onboarding map: map the feed's effective time, or its records state no time and the run checks report no age: REFERENCE.md `effective_at` row; onboarding map's defaults 2026-10-14 17:16 ET
  - [x] data-onboarding test: when the full installed proof is needed and how to run it: onboarding test step 2 points at mdm-engineering, "Choose the cheapest proof" 2026-10-14 17:16 ET
- [ ] How to work in this repo into `AGENTS.md` and `CLAUDE.md` (shared files: overlap guard first): affected tests (testmon, 5-minute cap), CI green before merge, watchers with a deadline, read the clock before a stamp, commit text from a file, secrets never printed, decide what follows from a ruling and ask only for approvals and merges
- [ ] History out of the how-to: PR numbers and dates outside Examples sections move to their tickets, keeping the rule they proved; the genericity lint refuses a PR number outside Examples
- [ ] Standing rule in `AGENTS.md` and `CLAUDE.md`'s task checklists: every ticket's checklist ends with "Learning → skill", naming the skill line it changed or "none"
- [ ] Claude's memory: notes now held in the repo are trimmed to a pointer
- [ ] Each part: review, CI green, merge on the operator's word
- [ ] Learning → skill: this ticket is the rule itself
