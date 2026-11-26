# Guide for Fold sightings into periods

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `docs/rules-try/link_periods.md` only. Words and the sighting-to-period case. Do not edit another guide. No test.

## Checklist

- [x] `docs/rules-try/link_periods.md` is the only file this ticket adds. No test. 2026-11-25 21:57 ET
- [x] The guide has the sighting and the period. Output taken from a run of ticket 28's family. 2026-11-25 21:57 ET
- [x] Learning → skill: none. A guide records what the page already does. 2026-11-25 21:57 ET

## Answer

`docs/rules-try/link_periods.md` lists the words with their stored keys, the invented sighting written in short words, the lines Show the full rule prints with the full sightings, and the period Try returns: `valid_from` the sighting's date, basis `observed`, `valid_to` and `valid_to_basis` null. It also records the run that a later sighting that still holds the capacity leaves the end null, a dropping sighting ends the period, a sighting after a stated end goes to `contradictions`, and the refusal for a typed end.

## Comments
