# 228: The two rulings skills hold no ticket, date or run count

Priority: 228, housekeeping. Map: [Rebuild priorities](../map.md). Opened 2026-11-11 19:54 ET (operator: "clean up the security-master and company-financials ticket citations too", then "remove the dates and run figures from the skills too also make skills focused on the task or the function it is created for"). Part of [214](214-skills-organized-one-index-one-link-script.md).

Type: task. Status: resolved (2026-11-11 19:54 ET).

## Checklist

- [x] (2026-11-11 19:54 ET) The last 20 ticket citations are gone (`security-master` 12, `company-financials` 8). A sentence that said a ticket "replaces" something now names the section that does; an "Evidence and sources" line gives the research file's path. The lint allows none now: `tests/unit/test_skills_cite_no_ticket.py`, `KNOWN` empty, 3 passed
- [x] (2026-11-11 19:54 ET) 69 dates removed from the three files: an operator's ruling keeps its words and loses its date; "decided" and "switched on" lose theirs. Verified by the date script: none left. Rule version names such as `2026-10-25.1` stay: they are names
- [x] (2026-11-11 19:54 ET) Run counts removed, each ruling kept with the shape of its evidence in words ("most", "a few", "about two thirds"): the holdings table, the OpenFIGI answer counts, the listings measurements, the cohort counts in `company-financials`. Tolerances and claims (5 per 10,000, a claim of 3) are rules and stay
- [x] (2026-11-11 19:54 ET) Not changed: what each skill says is live, decided or waiting for a switch-on. `security-master` still says the OpenFIGI rules wait for their switch-on, as the comment in `rules/merge/kinds/security.yaml` does
- [x] (2026-11-11 19:54 ET) Focus: both skills hold one domain's rulings and nothing else; nothing is moved out
- [x] (2026-11-11 19:54 ET) Genericity lint passes; the doctor's skill check returns nothing
- [x] (2026-11-11 19:54 ET) Learning → skill: none here; the rule and its lint land with ticket 214's closing PR
