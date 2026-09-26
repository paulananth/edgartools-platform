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
