# Guide for Prepare the MDM record

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `docs/rules-try/prepare_record.md` only. Words, the fixed-type case, and the missing-key refusal. Do not edit another guide. No test.

## Checklist

- [x] `docs/rules-try/prepare_record.md` is the only file this ticket adds. No test. 2026-11-25 22:08 ET
- [x] The guide has the fixed-type case and the missing-key refusal. Output taken from a run of tickets 31 and 32's family. 2026-11-25 22:08 ET
- [x] Learning → skill: none. A guide records what the page already does. 2026-11-25 22:08 ET

## Answer

`docs/rules-try/prepare_record.md` lists the four words with their stored keys, says "entity type rule" is not a word on this page, shows the invented row, source code, publication and a short contract with four words, the lines Show the full rule prints, the prepared record Try returns (entity type `company`, record key `R1`, identifier `ID-100`, cross-reference `TX-7`), and the refusal for a row with no key: `{"refused": "The record is set aside: missing_record_identity"}`.

## Comments

