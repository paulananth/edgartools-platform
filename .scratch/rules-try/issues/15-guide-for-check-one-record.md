# Guide for Check one record

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `docs/rules-try/check_record.md` only. Words and the "is present" case. Do not paste an in-reference check. No test.

## Checklist

- [x] `docs/rules-try/check_record.md` is the only file this ticket adds. No test. 2026-11-26 00:45 ET
- [x] The guide uses "is present" only. Output taken from a run of ticket 13's family. 2026-11-26 00:45 ET
- [x] Learning → skill: none. A guide records what the page already does. 2026-11-26 00:45 ET

## Answer

`docs/rules-try/check_record.md` lists four words with their stored keys (`is present` → `present@1`; `hold the record out` → `exception`; `keep off matching` → `withhold`; `count the failure` → `flag`), the invented record `{"name": "Example Works"}` and a record with no name, a short rule with two words, the lines Show the full rule prints, and the output Try returns for each case: a pass, `{"held out": "quality_name_required", "on_fail": "exception"}`, and the `withhold` and `flag` results. It says there is no in-reference check.

## Comments

