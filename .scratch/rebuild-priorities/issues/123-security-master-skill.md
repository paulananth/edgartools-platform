# 123: A Security master skill

Priority: 123 (operator, 2026-10-20 08:16 ET: "Create a security master skill
that codifies these rules"). Map: [Rebuild priorities](../map.md). Rules from
ticket 120's rulings (2026-10-15 to 2026-10-20) and `rules/merge/kinds/security.yaml`.

Type: task. Status: in progress (Claude, 2026-10-20). Blocked by: none.

## Checklist

- [x] `skills/security-master/SKILL.md`: hard stops; sources and ranking; keys, identifiers, cross-references; matching; every OpenFIGI field and the primary listing; the listings detail table; held-back reasons; run order; 13F-only Securities; proving. Each rule marked live (in `rules/`, proved) or decided (ruled, built in ticket 120), with the operator's words and date (2026-10-20 08:17 ET)
- [x] `link.sh`, `agents/openai.yaml`, as the other skills (2026-10-20 08:17 ET)
- [ ] ~~A row in data-platform's step table~~ deferred: `skills/data-platform/SKILL.md` is open in two other runtimes' worktrees (overlap guard); add it when they land
- [x] How a Security is merged (operator, 2026-10-20: "Read the merging rules and priorities and how it works in to the skill"): the six matching rules with when each was switched on, the review reasons, each identifier's contract and tolerance, survivorship's order (steward, source priority, latest effective, fixed tie-breaks, clears, conflicts kept), read from `rules/merge/kinds/security.yaml`, `policy.yaml`, `survivorship.py`, `binding.py` and the engine's `survivorship::rank` (2026-10-20 08:20 ET)
- [ ] PR, CI, merge
- [ ] Ticket 120 ticks each "decided" rule here as live when it lands
- [ ] Learning → skill: this ticket is the skill; ticket 120's later rulings are recorded in it
