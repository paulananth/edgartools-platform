# Guide for Link two masters

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `docs/rules-try/link_masters.md` only. Words, the emitted link, and the missing-start wait. Do not edit another guide. No test.

## Checklist

- [x] `docs/rules-try/link_masters.md` is the only file this ticket adds. No test. 2026-11-25 22:13 ET
- [x] The guide has the emitted link and the missing-start wait. Output taken from a run of ticket 25's family with ticket 26's words. 2026-11-25 22:13 ET
- [x] Learning → skill: none. A guide records what the page already does. 2026-11-25 22:13 ET

## Answer

`docs/rules-try/link_masters.md` lists the four words with their stored keys, what each input holds, an invented security `S1` and company `C1` with accepted masters `E1` and `E2`, the short link with four words, the lines Show the full rule prints, and the output Try returns: one `ISSUED_BY` link from `E1` to `E2` with a stated period and no review. It then runs the same inputs with no `link starts`: no link, and the review `unknown_relationship_start`. It notes that a claim's `effective_at` stands in for a missing start as an observed one, and that a missing or unbound other master waits as `unresolved_endpoint` with `missing: ["target"]`.

## Comments
