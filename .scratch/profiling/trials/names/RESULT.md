# 07b trial: an id from the name, on real data

Run 2026-10-06 18:52 ET; rerun after review fixes 2026-10-06 18:57 ET (dropped tokens are now tested as apart). Local copies only, with no request to any provider.

## Inputs

- **SEC:** the newest submissions file of every filer in the all-76230 capture (76,230 records: name, former names, state, business zip, the filer's own LEI).
- **GLEIF:** the Level 1 extract `cm08-gleif-all.jsonl` (Golden Copy 2026-09-11, 3,428,477 records). It is cut to the 12,834 records that can pair with a filer: the record's LEI is one a filer carries, or one of its folded names (legal or other) equals a filer's current or former name. The full extract outgrew this machine (8 GB of RAM, 3.5 GB of free disk): the first run filled the disk with DuckDB's temporary files.
- **The proving id:** the LEI a filer states (`--same lei=lei`).

Commands (about 5 minutes for the extract, about 1 minute for the run):

```
uv run --no-project --with duckdb --with pyyaml python .scratch/profiling/trials/names/extract.py <folder>
uv run --no-project --with duckdb --with pyyaml python skills/data-profiling/scripts/match_names.py \
  --left <folder>/sec.jsonl --left-key cik --left-name name --left-variants former_names \
  --right <folder>/gleif.jsonl --right-key lei --right-name legal_name --right-variants other_names \
  --same lei=lei --attribute state=jurisdiction --attribute zip=hq_postal --out <folder>/out
```

DuckDB now runs with a 2 GB memory cap and a 1 GB cap on its temporary files (`--memory`, `--spill`).

## Results

| Measure | Value |
|---|---|
| Pairs the LEI proves | 356 |
| Near-homonyms: equal folded names, different LEIs | 19 |
| Records `name_id@1` pairs one to one | 10,853 |
| Names held by two or more records, so not paired | 296 |
| Of the name pairings, both sides carry the LEI | 226 |
| ...and the name id agrees with it | 223 |
| ...and the name id contradicts it | 3 |
| Name pairings where the SEC filer states no LEI this GLEIF subset holds | 10,627 |
| LEI-proven pairs the name id does not pair | 130 |
| Homonym rate: SEC / GLEIF subset | 0.07% / 2.41% |

**The 3 contradictions are SEC records that state another party's LEI.** In each one, the name id chose the GLEIF record with exactly the filer's name.
- "22C Capital LLC" states Bloomberg Finance L.P.'s LEI, probably its filing agent's.
- "SunAmerica Series Trust" states SunAmerica Asset Management's LEI, its adviser's.
- "Evelyn Partners Investment Management LLP" states Evelyn Partners Asset Management Limited's LEI, a sister firm's.

So on the 226 pairs an LEI can check, the name id gave no wrong pairing. That is a check on 226 records, not a bar: the operator ruled out a fixed bar. It misses 130 of the 356 LEI-proven pairs, where the two sources spell the name differently or the name is held twice.

**The one-to-one figures are measured on the GLEIF subset, not on all 3.4 million records.** A name held once in the subset can be held again elsewhere in GLEIF, so 10,853 is an upper bound and the GLEIF homonym rate of 2.41% is a lower bound. On full data, run the tool where memory and disk allow the whole right side.

**What tells entities apart** (compare exactly; `name_id@1` keeps every token):
- series and year numbers (`series 11/3`, `trust 2023/2024`);
- Roman numerals (`fund xii/xvi`);
- letters for share classes and accounts (`account c/e`);
- whole words after a family name (`fidelity magellan/securities`).

**Name alone cannot decide** (seen both as variants of one entity and as different entities):
- `inc/llc`, `llc/lp` and `limited/ltd`;
- `i/ii` and `ii/iii`;
- `a/b` and `a/c`;
- `2023/2024`;
- a dropped `inc`, `llc`, `holdings`, `group` or `ii`: a name less one of these tokens is often another record's name.

A legal form or a share letter is therefore never folded on a name alone.

**May fold** (variants seen only on one entity, never apart): `l p`/`lp`, `co`/`company`, a dropped `the` or `and`, and misspellings (`ventures`/`venutes`). Some pairs on this list are renames of a fund family (`ing`/`voya`, `bny mellon`/`dreyfus`), not spellings, and must not be folded. `name_id@1` folds nothing. With every listed fold applied, 10,696 records pair one to one, 157 fewer than without folding, because folding makes more names held twice. Folding gains nothing here; it stays evidence for a later format version, which is the operator's call.

**Supporting attributes:** neither is good enough to decide a pair on its own.

| Attribute | Agrees on LEI-proven pairs | Separates near-homonyms |
|---|---|---|
| State of incorporation vs. GLEIF jurisdiction | 32% | 81% |
| Business zip vs. GLEIF head-office postal code | 68% | 35% |

## What this shows for the skill

- **Use a name only where no id exists.** Here, 10,627 of the name pairings are filers that do not state the LEI GLEIF holds. Those are the records an id made from the name is for.
- **Keep every token.** In this data it costs no pairings (folding gives 157 fewer), it keeps share classes, series and legal forms apart, and the LEI-proven pairs show no wrong pairing from it.
- **A name held by two or more records pairs nothing.** There are 296 such names in this run.
- **Never trust a stated id blindly either.** The 3 contradictions are errors in the stated id, not in the name.
