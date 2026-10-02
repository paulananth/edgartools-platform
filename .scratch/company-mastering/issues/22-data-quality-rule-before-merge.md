# Check data quality in its own rule, before the merge

Type: build
Status: in progress
Blocks ticket 21 (the cascade merge). Codex PR #738 merged (ad43cfac,
2026-09-28); nothing else blocks.

## Question

Operator, 2026-09-27, answering which matching design to build: "need data
quality checks before merge, dq will be a seperate rule, finally cascade
merge".

So the order is: a Data Quality rule decides which values are fit to use,
then the cascade (ticket 21) merges on the fit values only.

Research: [data-quality 01](../../data-quality/research/01-datakitchen-testgen-observability.md):
borrow TestGen's check ideas;
do not adopt the tool.

## Design (grilling with the operator, 2026-09-27, Q1-Q13 agreed)

1. **Owner:** the Rules skill: an onboarding quality step (after Infer,
   before Check) and a "quality" mode for live feeds. Bookkeeping runs it.
2. **File:** `rules/sources/<source>/quality.yaml`, its own Rules Database
   document (kind `quality`), own versions, operator approval. A check across
   sources (over-shared addresses) sits with the kind's merge rules.
3. **Checks:** value present, in a set, in a reference file, pattern, LEI
   check digit, placeholder, registered-agent address. On failure: `reject`
   (since 2026-09-28: `exception`, below)
   (set aside, blocks, as a defect), `withhold` (kept, never used to match),
   `flag` (counted). Defects block from day one.
4. **Fixes:** SEC name state marker to state of incorporation; an invalid
   code to empty; address standardized. A fix writes the corrected value
   beside the original and names itself on the record; MDM matches and
   merges on the corrected value.
5. **Runs** once per batch, before MDM and silver. A new version applies to
   new batches only; re-checking old batches is an explicit re-run.
6. **Proof:** a proving run on a pinned batch: exact counts and about 10
   examples per check and fix; no 95% bar.
7. **Report:** a count per check and fix in the run result.
8. **Over-shared address threshold:** measure 10, 25 and 100 entities per
   address; the operator picks.
9. **First users:** SEC Company and GLEIF.

Shape (Claude, 2026-09-27 20:47 ET): both batch paths call `adapters.normalize`
(`cli.py:205`, `gleif_source.py:495`), so quality applies there, to the mapped
fields, before the record's fingerprint. Activation folds the active quality
version into the Dataset Contract it registers (`contract.quality`);
`register_dataset` already makes a changed contract a new mapping version,
so a new quality version applies to new batches only.

## Two changes to the agreed design (Claude, 2026-09-28, under the operator's
"you can own every thing ... move forward and fix")

1. **Q2, the file's home.** `quality.yaml` is its own file with its own
   version name, but not its own Rules Database document kind. The loader
   puts it into each Dataset Contract as `contract.quality`, as
   `files.policy()` composes the kind files. Why: #738 made registration
   (`change_journal/authority.registration_authority`) and Bookkeeping's
   `source_input` require the registered contract to equal the approved
   source document exactly, so a separate document would need a second
   approval chain threaded through both. One approval now covers the
   mapping and its checks, and a quality change is a new mapping version,
   which applies to new batches only (Q5). Reversible: a later kind can
   carry the same block.
2. **Q4, the address fix only.** A standardized address is a matching copy
   (`matching.address`); the address MDM shows stays as the source wrote
   it. Why: "3050 BOWERS AVE" is a better key but a worse value to show.
   The value-correcting fixes ("DC" to empty, "/DE" to DE) do change the
   field MDM shows and merges on, as agreed; the original stays on the
   record.

## GoF consult (2026-09-28)

Leave the structure. One hook in `adapters.normalize`, which all three
readers call (`cli.batch_input`, the native GLEIF reader, Bookkeeping's
`source_input`); checks and fixes are a fixed table of functions, as the
matching tests are.

## Operator ruling, 2026-09-28 (recorded 08:13 ET): exceptions, not stops

"A record with no name is set aside and stops the run ... Do not stop make
few critical data elements if it is missing mark it so it never tries to
merge it becomes an exception that needs to be fixed or ignored".

So `on_fail: reject` became `exception`: the record is set aside as
`quality_<id>`, never merges, and never stops the run (the contract lists
the reason as non-blocking; registration refuses a contract that does not).
It is an open review item. The one critical data element today is the name,
for SEC and GLEIF. Closing an exception ("fixed or ignored") has no command
yet: a follow-up ticket.

## Proof (2026-09-28 08:31 ET)

Inputs: all 76,230 SEC filers (`cm08-sec-scan.jsonl`, `bdf379bf…c0d1`) and
the 2026-09-11 GLEIF Golden Copy (`cm08-gleif-all.jsonl`, `e4e6fe8a…d9f`).

SEC (`sec-company-quality-v1`), through the production `normalize`: 5,477
filers reach the quality rule; 70,753 are held back earlier as not
companies (the classification rule).

| What | Records |
|---|---:|
| "DC" state emptied | 3 (Applied Materials becomes DE from its "/DE" tag; National Rural Utilities stays DC from its "/DC/" tag; Core Natural Resources becomes unknown) |
| State filled from the name tag | 11 (Park Ohio: OH; Northrop Grumman: DE; Charter: MO) |
| Address copy differs from the source's | 4,799 |
| Address withheld: a registered agent's | 7, all real agents (1209 Orange St, 251 Little Falls Dr, 2711 Centerville Rd) |
| Exception: no name | 0 |

GLEIF (`gleif-quality-v1`), GENERAL entities, as its contract maps them.
GLEIF gives two addresses (operator, 2026-09-28: "we have multiple
addresses in lei feed"): the legal address, which MDM shows, and the
headquarters address, now also kept for matching
(`matching.headquarters_address`). Each is fixed and checked on its own.
84% of LEIs give the same address twice.

| What | Legal address | Headquarters address |
|---|---:|---:|
| Records | 3,043,262 | |
| Copy differs from the source's (not only in case) | 1,876,914 | 1,881,276 |
| Withheld: a registered agent's | 124,852 | 16,860 |
| Withheld: a placeholder street ("N/A", "n.a.") | 5,398 | 4,462 |
| Exception: no name | 0 | |

The address a match can use, headquarters first, else legal:
headquarters 3,000,424 (98.6%), legal 6,254, none 36,584.

The first run showed three wrong rules, fixed before this one: a bare
"C/O" marker withheld companies' own offices ("C/O LOGITECH INC"); GLEIF
had no placeholder check (4,144 Finnish "N/A" streets); letters outside
A-Z were dropped, so Greek streets read as "0" and "FLATBUSH" lost "FL".

Over-shared addresses (Q8), on the address a match uses:

| Threshold | Addresses | Entities withheld |
|---|---:|---:|
| more than 10 | 12,128 | 403,384 |
| more than 25 | 3,604 | 271,352 |
| more than 100 | 496 | 133,289 |

No SEC address is shared by more than 10 filers. The largest are corporate
service providers (C/O Rathbone Investment Management: 5,685; Vistra
Corporate Services Centre: 2,701; PO Box 309, Cayman: 1,811) and the real
headquarters of large groups with many legal entities (200 West St, New
York: 3,452; 650 Newport Center Dr: 1,953; 30 Hudson Yards: 1,709). The
operator picks the threshold.

## What this ticket leaves to others

- **Withhold takes effect with ticket 21.** Today's two matching rules read
  `matching.business_postal_code` and the GLEIF headquarters postcode, not
  the address the quality rule withholds, so an agent's ZIP still counts in
  them. Left on purpose: withholding it now removes about 961 of today's
  3,050 merges (ticket 21's veto measurement), a matching change the
  operator decides with ticket 21's passes, which read `matching.address`.
- **The over-shared address check** (Q2, Q8) waits for the operator's
  threshold; it then goes in the Company merge rules.
- **Silver** (Q5): there is no Clean silver writer yet; it reads the same
  fixed values when it is built.
- **"Unique"** (the plan's list, not Q3's): not built; the record key already
  refuses duplicates.

## Three-axis review (2026-09-28 07:50 ET), what changed

- Standards and Spec: a withheld street now withholds the whole address too;
  a contract with no `matching` block keeps the address copy; the address
  copy counts as a fix only when it differs, with the source address as the
  original, and leaves out the suite and floor (the plan's "suite
  removed"); `write_source` refuses before it writes; the LEI test reuses
  the identifier check (`adapters._lei`); the args a fix corrects sit in
  its `FIXES` entry.
- GoF: each Rules document kind's read and write is one entry in
  `files.LAYOUT`, used by `save`, `export`, `migrate` both ways. This also
  fixes `rules save --merge` and `export --merge`, which read and wrote
  `merge/policy.yaml` alone, without its kind files and reference tables.
- Proving script: SEC records now go through the production `normalize`
  with the reader's landing-row shape; GLEIF is rebuilt as its contract maps
  it; over-shared addresses are counted per source and across both.

## Checklist (times ET)

- [x] `/gof-refactor-reviewer` on the Merge Stage and the rules loader.
- [x] The file format and its loader (`files.load_source`/`write_source`);
  no Rules Database kind (change 1 above).
- [x] The quality step in `normalize`: fixes, then exception, withhold, flag
  (`edgar_warehouse/mdm/clean/quality.py`); matching skips withheld values.
- [x] `rules/sources/sec.submissions.company/quality.yaml` and
  `rules/sources/gleif/quality.yaml`, the first checks and fixes.
- [x] Counts per check and fix in the run result (`quality` in the MDM run
  result and in the Bookkeeping MDM receipt) (2026-09-28 07:38 ET).
- [x] The Rules skill: step 5 "Quality", the quality mode, REFERENCE.md
  "Data quality" (07:30 ET).
- [x] Proving run on the ticket 08 inputs (2026-09-28 08:31 ET):
  [`22-quality-proving-run.py`](../research/22-quality-proving-run.py), result
  [`22-quality-proving-run.json`](../research/22-quality-proving-run.json)
  (counts, up to 10 examples each, input sha256s). Below.
- [ ] Full suite, three-axis review, PR, CI; merge on the operator's word.
