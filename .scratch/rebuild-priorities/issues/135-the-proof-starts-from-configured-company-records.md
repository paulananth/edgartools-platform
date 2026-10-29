# 135: The recreation proof starts from configured Company records

Priority: 135, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md).
Opened 2026-10-22 from the map review ("review all existing ticket and provide a
way to complete the project").

Type: task. Status: in progress (Claude, 2026-10-29; operator, 2026-10-29 07:33 ET: "Take over 135").
Blocked by: nothing on this map (#1121 and #1142 merged).

## Question

[32: the recreation proof](32-profiling-08-recreation-proof.md) defers its
baseline and its cold-agent run to one unchecked item of the
`sec-configured-fields` workstream
(`.planning/workstreams/sec-configured-fields/TICKET.md`, line 9): "retire
Company preparation/census/provenance and GLEIF release/semantic consumers;
prove whole-source census and installed 6,414 Company / 3,052 CIK+LEI
population/recovery". Mastering starts from SEC Company records (GLEIF alone
binds nothing), and the Company input is still the retained Company
preparation that item retires; a baseline taken today would measure a path
about to be removed. Neither #1121 nor #1142 ticked it (checked 2026-10-22
21:11 ET).

What is left before 32's baseline can run:
- the Company records come from the configured source extract, combine and
  `mdm.prepare` chain, never the retained preparation;
- the census and provenance consumers read the configured outputs;
- the installed population proof repeats: 6,414 Companies and 3,052 CIK+LEI
  bindings from an empty store, a second pass changing nothing.

The item sits in another runtime's workstream file. Nothing is owned by Codex
(operator, 2026-10-16), and the overlap rule still applies: take it over only
on the operator's ruling, then build on Codex's merged work, never beside an
open branch.

## Checklist

- [x] Operator's ruling (2026-10-29 07:33 ET): "Take over 135": Claude takes the item over (asked 2026-10-22,
  then "skip this move to next"). No Codex PR is open (checked 07:35 ET); the overlap guard still runs on every commit
- [x] The item's remaining parts, from the workstream files (2026-10-29 07:35 ET): the item is
  `.planning/workstreams/sec-configured-fields/TICKET.md` line 9; its parts are spread over
  `company-preparation-cutover` and `whole-source-census`. On today's `main`:
  - Legacy record mapping: none left (`legacy_pair_comparison` and `legacy_jurisdiction_table` are configuration
    keys of the mastering catalog, not old code). Done.
  - Company preparation: configured since #880 (2026-10-09): `company_prepare.py` only binds the approved run
    IDs and the census digest into the `mastering` target's configured steps (read, combine, `mdm.prepare`,
    `mdm.merge`). Done.
  - The Name Frequency census (`mdm name-census`): still built in Python (`name_frequency.py`, `name_census.py`,
    GLEIF's input checked by `gleif_publication`), over configured readings; the whole-source comparison to
    original-source EOF passed (2026-10-09). Open in `whole-source-census`: "Express complete source census
    construction in bundled Rules, with immutable source/context receipts and separate worker verification",
    then replace its consumers and retire the Python construction
  - The installed population proof (6,414 Companies, 3,052 CIK+LEI from an empty store, an unchanged replay and
    recovery): passed 2026-10-10, -11 and -11 (#906 and the raw-capture bundles); MDM storage changed since
    (governed storage, #1152-#1190), so it runs again on today's `main` before 32's baseline
- [ ] The census construction as a configured Bookkeeping target in Rules (source extract, combine), each step
  verified by its own worker; equal to today's Python census on the whole capture (the 2026-10-09 file sha256)
- [ ] The census consumers read the configured target's output; the Python construction retired, an
  independent test-only oracle kept until the configured one is proven
- [ ] The installed population proof on today's `main`: 6,414 Companies and 3,052 CIK+LEI from an empty store,
  a second pass changing nothing, recovery (runs after ticket 120's loads, which hold the machine until about
  13:00 ET)
- [ ] Built, reviewed (Standards, Spec, GoF), PR, CI green, merged
- [ ] 32's two deferred parts re-opened on this ticket's merge
- [ ] Learning → skill
