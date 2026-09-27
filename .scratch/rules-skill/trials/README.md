# Trials of the `rules` skill

The operator asked on 2026-09-26: "must test skill on company entity for
each source from scratch and fine tune and fix the skill". Each trial gives a
fresh agent only the skill, a copy of the repo without the source's rules
file, and the source's captured files. What the agent writes is scored
against the proven file in `rules/sources/`.

- `score.py <proven source.yaml> <trial source.yaml>` pairs each proven
  contract with the trial contract for the same record type. It compares
  every adapter key plus `nonblocking_deferred_reasons` and
  `publication_families`, reporting each as equal, different, missing or
  extra. The envelope's free text is printed, not scored.
- The pass bar and the round cap are in ticket 07. They were written before
  round 2 ran.

## Round 1 (2026-09-26 16:41–18:00 ET)

| Source | Inputs | Equal | Different | Missing | Extra | Questions | Skill gaps |
|---|---|---|---|---|---|---|---|
| [SEC submissions](round-1/sec/) | latest submissions JSON for 40 CIKs from prod bronze; both ticker lists (2026-09-02) | 26 | 0 | 8 | 0 | 9 | 12 |
| [GLEIF](round-1/gleif/) | the three Golden Copy zips, 2026-09-11 16:00 UTC | 50 | 5 | 20 | 10 | 10 | 13 |

**Not a from-scratch measurement.** Both agents read repo tests that restate
the mapping, and the SEC agent also read the Source Contract spec. The
questions were assumed, not answered. Each folder holds the agent's log (with
where every decision came from), the file it wrote, its score and its small
scripts.

Prompt given to each agent (the sandbox path and the input description
differed):

> You are a fresh agent in a trial of a new skill. Your only instructions for
> the work are in the skill file. Follow it. Sandbox (your whole world): …
> `repo/` is a copy of a code repository (no git history). The skill is
> `repo/skills/rules/SKILL.md` (with `REFERENCE.md`). `inputs/` holds a
> source's captured files. Your task: onboard the source whose files are in
> `inputs/`, using the skill's "Add a source" steps. Rules: stay inside the
> sandbox; run Python with `uv run --no-sync`; no requests to the source and
> none to any SEC domain; you cannot reach the operator, so log each
> question with your recommendation, assume it and continue, but never
> assume an approval; edit nothing but the new source's folder; keep the
> skill's log and record where each mapping decision came from; report the
> file, the log, the question count, the missing commands and every unclear
> or wrong thing in the skill.

## Round 2 (2026-09-26 18:40–20:15 ET)

- **Sandboxes.** No `tests/`, `.scratch/`, `.planning/` or Source Contract
  spec. The GLEIF sandbox also has none of the GLEIF docs that restate its
  mapping.
- **Two phases.** In phase A the agent works up to the questions and stops.
  Answers come from the written record only; see
  [answer-key.md](round-2/answer-key.md) for how each question was tagged.
  In phase B it writes the file and dry-runs it.
- **Operator answers during the round.** Question 5 of the SEC trial was
  answered by the operator directly: keep EIN and SEC's LEI as lookup-only
  identifiers; tickers belong to Security.

| Source | Equal | Different | Missing | Extra | Questions | Should have inferred |
|---|---|---|---|---|---|---|
| [SEC submissions](round-2/sec/) | 25 | 0 | 9 (all `provenance`) | 1 (EIN, the operator's new decision) | 5 | 1 (the address) |
| [GLEIF](round-2/gleif/) | 64 | 2 | 9 | 11 | 9 | 3 (names, family, address) |

**What round 2 still misses:**
- **SEC:** the reader's trace fields (`provenance`).
- **GLEIF Level 1:** the sole-proprietor kind. The record leaves it unnamed;
  the agent chose Person.
- **GLEIF relationships:** the agent never asked which relationship types are
  in scope, and added four fund and branch types.
- **Design choices that differ from the proven file:** the relationship
  record key, and an `lei` identifier on relationship and exception records.
  These are real decisions, not errors.

**Not a pass** under the ticket 07 bar. Round 3 is the last round before the
results go to the operator.

## Round 3 (2026-09-27 04:47–13:14 ET), the last round under the cap

Same sandboxes and two phases as round 2. Answer key and tags:
[answer-key.md](round-3/answer-key.md).

| Source | Equal | Different | Missing | Extra | Questions | Should have inferred |
|---|---|---|---|---|---|---|
| [SEC submissions](round-3/sec/) | 25 | 0 | 9 (all `provenance`) | 2 | 8 | 0 |
| [GLEIF](round-3/gleif/) | 69 | 6 | 0 | 3 | 12 | 4 (names, family, both blocking questions) |

**Better than round 2.** GLEIF has no missing keys (round 2 had 9). The agent
asked which relationship types are in scope, which round 2 never did, and it
wrote the kinds, identifiers, fields and address exactly as proven. SEC asked
nothing it should have inferred.

**Every remaining difference, sorted:**
- **The operator's later decisions (the proven SEC file is behind them):** the
  9 SEC `provenance` keys (trace beside the record) and the extra `sec_ein`
  (lookup only).
- **Real open questions for the operator:**
  - SEC: the agent made filers held back by the Company rule non-blocking. The
    record keeps them blocking; "wait in the Stage" was recommended, never
    decided.
  - GLEIF: the agent made `unsupported_relationship_type` non-blocking on all
    three members (4 of the 9 GLEIF differences). Under the proven file a fund
    or branch link whose two ends are both in the approved Company list blocks
    the run, although the record says those links "stay as captured source
    evidence". The proven file may be wrong here.
- **Skill gaps:**
  - The relationship record key: the agent profiled GLEIF's unique key as
    start, end, type, then wrote start, type, end. Key order changes each
    record's identity. The skill should say: keep the source's own key order.
  - The relationship `scope` text is a free label (no code reads it). The skill
    should give a form for it: `<provider> <relationship family>`.

**Not a pass** under the ticket 07 bar: GLEIF asked 4 questions the skill
should have answered, and 6 keys differ. Per the cap, the results go to the
operator.
