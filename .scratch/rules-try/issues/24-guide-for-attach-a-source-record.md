# Guide for Attach a source record

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `docs/rules-try/attach_record.md` only. Words and both cases. The title says this is source record binding. Do not edit another guide. No test.

## Checklist

- [x] `docs/rules-try/attach_record.md` is the only file this ticket adds. This ticket file and `.scratch/rules-try/map.md` also changed. No test. 2026-11-25 23:08 ET
- [x] The title says this is source record binding. `docs/rules-try/attach_record.md`. 2026-11-25 23:08 ET
- [x] The guide has the one-master case and the two-master case. The outputs were run on the Attach a source record page. 2026-11-25 23:08 ET
- [x] Learning → skill: none. A guide records what the page already does. 2026-11-25 23:08 ET

## Answer

`docs/rules-try/attach_record.md` is titled "Source record binding: attach a source record". It lists each word and its stored key (same identifier, how many that identifier allows, attach, create a master, send to review), where each goes in the policy, the refusals (a bare stored key, a word for combining two existing masters, the words of other families), what to paste, an invented policy for the ticker `EXMPL` and one record, and the outputs: one pasted master returns attach (stored `bind`, master `M1`); two pasted masters return send to review (`ambiguous_identifier`); no master returns create a master (stored `mint`). The outputs are what the family returned when run.

## Comments

