# Resume a source's work

A session picks up a source where another stopped: it repeats no finished work and trusts no result whose inputs
changed. Data Platform owns the record's fields and the resume decision; each phase's owner writes its own evidence
into the record and decides, under its own rules, when its phase is complete.

## The record

The record is one `## Resume` section at the top of the source's existing log, never a separate state file:

- a new source: `.scratch/onboarding/<source>/onboarding-log.md` ([data-onboarding, The log](../data-onboarding/SKILL.md#the-log));
- a live feed's rule change: `.scratch/onboarding/<source>/refining-log.md` ([refining-rules](../refining-rules/SKILL.md#shared-with-data-onboarding)).

A run is recorded by its run id alone. Bookkeeping status (`edgar-warehouse bookkeeping status <run_id>`) is the
authority for its units, and the Change Journal for its processed files; the log never copies either.

Write the record when a phase finishes or stops, before handing off. Public values only: names, paths inside the
repository, hashes and counts, never an address, a login or a data value.

| Field | Record | Reused when | Reopened when | Blocked when |
|---|---|---|---|---|
| Source | Its name; the rules folder in use (`EDGAR_RULES_ROOT`, or the bundle's copy); its rules files' identity (in a checkout with no uncommitted change there, `git rev-parse HEAD:rules/sources/<source>`; elsewhere each file's sha256; `none` before they exist); the capture location and its manifest's sha256 | The name, rules identity and capture hash all match | The rules identity differs, or another delivery is the selected capture: every phase whose evidence used it reopens | The recorded capture or its manifest is missing, or no longer hashes as recorded (captured files never change, so report it as a defect) |
| Phase | The current mode and part (data-onboarding's or refining-rules' modes, or a data-operations run); each completed phase with each artifact's path and sha256 (profiling's `REPORT.md` and `findings.yaml`, a run id) | Every artifact is present with its recorded hash | An artifact's hash differs, or an input it was made from reopened: that phase and every later one reopen | A recorded artifact is missing |
| Owning skill | One of data-profiling, data-onboarding, refining-rules, data-operations | The [Decisions table](SKILL.md#decisions-artifacts-and-handoffs) gives the same owner for the current state | The state moved (a new source's version became active, so its rule changes go to refining-rules): the new owner starts from the recorded artifacts | The state fits no owner or two |
| Installed bundle revision | For data-platform's and the owning skill's folders: a copy made by `edgar-warehouse skill install` gives the first word of its `.installed-by-edgar-warehouse` (the installed tree's digest); a linked copy gives the commit of the checkout it links to (`git -C <checkout> rev-parse HEAD`, with no uncommitted change under its `skills/`). The engine's ref is the `REF` chosen at [Setup](SKILL.md#0-setup), step 1, written into the record then | The revision matches | The revision differs: re-read the owner's entrypoint, run `edgar-warehouse doctor`, and re-prove what an engine command made outside a run by the owner's cheapest proof ([carry a proof forward](../mdm-engineering/SKILL.md#choose-the-cheapest-proof) when its rules alone moved). A Bookkeeping run keeps the runtime it was frozen with, so a changed ref does not reopen it | A revision cannot be read, or the ref was never recorded: treat it as changed, never as matching |
| Configured connection names | The duty; the env file's name; the variable names it must set (`DATA_URL`, `CONTROL_URL`, `CONFIG_URL`); each store's `doctor` state (`answers`, `not set`) | Same duty, the file exists and sets each variable, and each store's state matches | The duty differs, or a store's state changed: run [Start here](SKILL.md#start-here-route-the-work) steps 3 and 4 again | The file or a variable is missing (the operator sets it in their own terminal), or a store `does not answer` |
| Next action | The owner's step by name and link, and within it what is done and what is not, as a checklist | Every field above is reused | Any field above reopened: the next action is the earliest reopened phase's first step | Any field above is blocked |

## Resume

1. **Read the record** in the source's log. With no `## Resume` section, there is nothing to resume: route from
   [Start here](SKILL.md#start-here-route-the-work).
2. **Check each field** in table order against what is there now: hash each recorded artifact, read the rules identity
   and the bundle revision, check the duty file's variables without printing a value. The first field that is
   blocked stops the resume; name the blocker to its owner.
3. **Pick the next action.** All reused: the recorded next action, at its first unchecked item. Some reopened: the
   earliest reopened phase's first step, its owner the owner of that phase.
4. **Run `edgar-warehouse doctor`** as [Start here](SKILL.md#start-here-route-the-work), step 4, says.
5. **Hand off** the recorded artifacts and the next action to the owner. The owner updates the record.

**Unchanged inputs repeat nothing.** A completed phase whose fields are all reused is not run again, its artifacts are
handed on as they are, and a stopped load is resumed by running the same `edgar-warehouse load` again: the Change
Journal skips each file already processed with the same source, key, content hash and processing identity.

**Changed inputs reuse no proof.** A reopened phase's earlier artifacts stay where they are, marked reopened in the
record with the field that reopened them; nothing is deleted and no pinned version is silently repinned
([Source readiness](SKILL.md#source-readiness)). Its proof is made again by its owner, or carried forward only where
the owner's rules allow it.

**Unfinished work stays visible.** The next action's unchecked items are left unchecked until the owner's evidence
completes them; a resume never ticks an item the earlier session did not verify.

## Example record

Invented values, the shape only:

```markdown
## Resume

- Source: `example.feed`; rules folder `EDGAR_RULES_ROOT`; rules identity `none`; capture `captures/example.feed/2026-01`,
  manifest sha256 `3f9a…`
- Phase: map, part 1. Done: profile (`REPORT.md` sha256 `81c2…`, `findings.yaml` sha256 `07de…`)
- Owning skill: data-onboarding
- Installed bundle revision: data-platform tree `5b1e…`, data-onboarding tree `9c40…`; engine ref `a1b2c3d`
  (recorded at Setup)
- Connection names: duty none (captured files only); every store `not set`
- Next action: data-onboarding, map, part 1
  - [x] identifiers mapped
  - [ ] fields 13 to 20
```
