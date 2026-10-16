# An identifier rule may create a Company only after the name rules

Priority: 99, tier 1, blocks ticket 22's resolution. Map: [Rebuild priorities](../map.md).

Type: task (engine code, small). Status: closed, replaced by configuration (operator, 2026-10-16: "why are you codeing merge.py all must be configured", then "Wait, config only (Recommended)"): `gleif-issuer-lei` joins the one Company holding the LEI and otherwise waits for the name rules; it creates no Company. The engine is unchanged. Blocked by: none. Blocks: 22 (ISSUED_BY by issuer LEI).

## Why

Ticket 22's Proving Run 2 (2026-10-16): 3,240 N-PORT issuers became a second Company beside the SEC Company the SEC–GLEIF name rules would have bound them to; only 288 joined. The cause is rule order (`edgar_warehouse/mdm/clean/merge.py:167-187`): identifier rules propose first, and a record they bind is not name-matched. `gleif-issuer-lei` (`on_no_match: mint`) creates the Company from the GLEIF record before the name rules see it.

Ruling (operator, 2026-10-16: "Name rules first (Recommended)"): the issuer rule creates a Company only for a GLEIF issuer no SEC–GLEIF name rule binds.

The order cannot flip for every identifier rule: an SEC record's CIK rule must create its Company first, so a GLEIF record joins it by name in the same batch (ticket 08).

## Proposed change

A binding rule may state that its creation waits for the name rules (for example `on_no_match: mint_after_names`). Its joins (one Company already holds the identifier) stay first; its creations are proposed after the name rules, only for records they left unbound. Every other rule is unchanged.

## Checklist

- [ ] ~~Operator's word to code it~~ not coded: the operator ruled configuration only 2026-10-16 14:39 ET
- [ ] ~~GoF consult; the rule option, its policy check and tests (joins first; a creation waits; a name-bound record creates nothing; other rules unchanged)~~ replaced by `on_no_match: wait` (ticket 22)
- [ ] ~~`gleif-issuer-lei` uses it; pinned digests by layer~~ replaced by `on_no_match: wait` (ticket 22)
- [ ] Ticket 22's Proving Run 3: duplicates against today's 3,240
- [ ] Review, PR, CI green, merge on the operator's word
- [ ] Learning → skill
