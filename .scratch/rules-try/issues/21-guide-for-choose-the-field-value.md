# Guide for Choose the field value

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `docs/rules-try/field_value.md` only. Words and the directory-then-register case. Do not edit another guide. No test.

## Checklist

- [x] `docs/rules-try/field_value.md` is the only file this ticket adds. 2026-11-25 22:15 ET
- [x] The guide has the directory-then-register case, with the words, the stored keys, the invented claims and the output of ticket 19. 2026-11-25 22:15 ET
- [x] Learning → skill: none. The guide records a case the family already runs. 2026-11-25 22:15 ET

## Answer

`docs/rules-try/field_value.md` lists the four words with their stored keys and where each goes, the six inputs the page asks for, and the directory-then-register case: two invented subjects whose claims disagree on `name` and `address`, a short policy that ranks the register first for every field and the directory first for `address`, the lines and full policy that Show the full rule prints, and the output Try returns (`address` from the directory, `name` from the register, the loser under `conflicts`). It states that source priority chooses a field value and never decides that two masters are one subject. No test.

## Comments

