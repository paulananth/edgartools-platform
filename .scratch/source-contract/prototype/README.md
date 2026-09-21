# PROTOTYPE — Source Contract runner and two Source Contracts

Throwaway code for [ticket 07](../issues/07-prototype-gleif-and-form-345-source-contracts.md).
It answers one question: **do the decisions in tickets 04–06 hold on real
sources?** It is not production code. Codex builds the real engine from the
spec (ticket 08).

## Run it

```bash
cd .scratch/source-contract/prototype
./source prove sources/form345 --gate --proof-dir rules_db   # Proving Run: validate → cases → checks → gate
./source prove sources/gleif   --gate --proof-dir rules_db   # includes one merge case (needs Colima + postgres:16-alpine)
./source prove sources/gleif --json                          # the agent-facing output
./source mapdoc sources/form345                              # generated Mapping Document
uv run --project ../../.. --offline --with ruamel.yaml --with jsonschema python engine/selftest.py   # as-of lookup
R18=… PROTO=$PWD uv run --project ../../.. --offline --extra s3 --extra mdm-runtime --with ruamel.yaml --with jsonschema python equivalence.py
```

Local inputs only: the Form 3/4/5 gate reads the local copy of production
bronze taken for Person research 18 (`$R18`, 5,356 artifacts, 17,956
`submissions.json`); GLEIF reads the 316 real Level 1 records extracted by the
GLEIF research. The runner refuses network access; only the merge harness
re-opens `127.0.0.1` for its throwaway Postgres.

| Path | What |
|---|---|
| `engine/source_engine.py` | the runner: loader, readers, 23 primitives, custom-step API, checks, gate, proofs, Mapping Document, output |
| `engine/contract.schema.json` | the JSON Schema (editor autocomplete via the modeline in each contract) |
| `engine/merge_harness.py` | `expect.merge` cases through Clean MDM's real Merge Stage in a throwaway Postgres 16 |
| `engine/selftest.py` | as-of lookup on a synthetic dated layout |
| `families.local.yaml` | engine config: artifact family → where it sits on this machine |
| `policies/mastering-policy.yaml` | Rules Database stand-in: a Mastering Policy authored in the same YAML convention (Q2a) |
| `sources/form345/`, `sources/gleif/` | contract, fixtures, custom code (Form 3/4/5 only), generated `MAPPING.md` |
| `rules_db/` | proofs written by `--proof-dir` (stand-in for the Rules Database) |
| `expected-differences.md`, `equivalence.py`, `equivalence.json` | Form 3/4/5 against `ownership.py` |

## Results

| | Form 3/4/5 | GLEIF Level 1 |
|---|---|---|
| Equivalence with today's parser | **5,356 / 5,356 artifacts identical, 0 unexpected differences, 0 path errors** (the comparison was checked to be real: un-ignoring `parser_version` makes all 683 rows of a 200-artifact sample differ) | no production parser exists |
| Named cases | 5 pass (joint filing, company owner, C/O address, See Remarks, synthetic dropped transaction) | 2 pass, incl. one merge case |
| Gate | 5,356 artifacts, 5,743 owner + 10,964 transaction rows, 15 s, 0 rejects, 0 violations on 4 checks | 316 records, 1 declared exception with `why:` |
| Contract length | 227 lines | **93 lines incl. tests (check 10)** |
| Custom | 2 of 60 columns (3.3%): `owner_display_name@1`, `owner_kind@1` | 0 of 17 |
| State | proven (`rules_db/sec.ownership/…proof.json`) | proven (`rules_db/gleif.level1/…proof.json`) |

## Acceptance checks exercised

| Check | Result |
|---|---|
| 1 source-local change | each source is one folder: contract, fixtures (incl. its own lookup fixtures), optional `custom.py` |
| 2 delete a source | GLEIF folder deleted → Form 3/4/5 still proves |
| 3 engine names no source | grep for form/gleif/ownership/rptOwner/lei/sec./edgar in `source_engine.py`: none |
| 4 no network | socket connect refused process-wide; the merge harness re-opens localhost only |
| 6 Mapping Document generated | `sources/*/MAPPING.md`, from the contract and the adapter block |
| 8 one command | `./source prove <dir> --gate` |
| 9 line and rule | argument typo → `INVALID …:15 [argument-known] … did you mean 'default'?`; YAML syntax, path syntax and silver type errors all name a line |
| 10 GLEIF ≈100 lines | 93 |
| 11 custom fraction shown | in each `MAPPING.md` |
| 5, 7 | not exercised here (ticket 09; glossary review in ticket 08) |

## Findings for the spec (ticket 08)

1. **The language holds.** Research 02's vocabulary, with restricted dotted
   paths, `each:` groups and `steps:` chains, reproduced a real production
   parser exactly and read a real outside source with no custom code.
   Reading `<value>` (`.value.$`) instead of all descendant text changed 0 rows.
2. **The adapter needs a kind per row at mapping time, but rule C-J is a
   Mastering Policy classification.** The prototype fills `owner_kind` with a
   declared custom step using edgartools' classifier. That is *not* C-J, and it
   is only a stand-in. **Codex proposal:** let a Dataset Contract defer the
   kind to the policy's classification rules, or define a provisional kind the
   policy may override. Without one of these, C-J cannot sit where the policy
   language put it.
3. **A JSONPath habit breaks YAML before it reaches the path rule.**
   `LegalName[*]` is read as a YAML alias. The loader must translate YAML
   errors into line-and-rule errors (fixed here), and the path rule must be a
   whitelist (names, `@attr`, `$`, `prefix:Name`), not "no dots or spaces".
   The first version accepted a quoted `"LegalName[*].$"`.
4. **A silver type mismatch is a contract or data failure (exit 1) located
   at the silver column, not an engine bug (exit 3).** The first version got
   this wrong.
5. **Test-case lookups must read the source folder's own fixtures**
   (`fixtures/families/<family>/`), never machine bronze. Otherwise a case
   depends on the laptop.
6. **YAML anchors (`&txn`, `<<:`) were used to share the eleven transaction
   columns between two tables.** They work (ruamel), but they are a second way
   to write the same thing. The spec should either allow them explicitly or
   add a named `columns_from:`.
7. **Envelope header fields** (the SGML `ACCESSION NUMBER`, `FILED AS OF
   DATE`) are reader output, read with a `header` primitive. The accession
   number is not in the ownership XML.
8. **As-of lookup:** proven on a synthetic dated layout (`engine/selftest.py`,
   6/6). It is *not* proven by the equivalence run, because the local
   submissions copy is flat. The path date is the fetch date by construction
   (`dataset_path_catalog.py:215-219`). S3 object times are the 2026-07-19
   migration copy, not capture times, and must never be used.
9. **Merge cases work as designed** through Clean MDM's real Merge Stage:
   seeds go through the same contract plus a declared Steward bind, and
   identities are named by the case. One case costs about 10–15 s including
   container start; a 60 s readiness wait was needed. Planted wrong
   expectations all fail. `bound` checks a declared binding until Codex's
   automatic-rule test mode exists.
10. **Exit code when cases pass but the gate was not run:** the prototype
    exits 0 with state `draft`. The spec should give it its own code, so an
    agent never reads "0" as "proven".
11. **`requires:` names distributions; imports name modules.** Map them with
    `importlib.metadata.packages_distributions()`, never a hand-written alias.

## Limits

- GLEIF was read from a 316-record JSONL extract, not the 928 MB zipped
  Golden Copy. The streaming zip reader is not exercised.
- Codex's `publication_v1` GLEIF fixture is synthetic (`key`, `name`). Its
  adapter *shape* is reused, but real Golden Copy paths are used for parsing.
- The Rules Database is a folder of proof files. `source save`, `export`,
  lifecycle states and Rule Activation Approval are not prototyped.
- Checks 5 (cold onboarding) and 7 (every term in `CONTEXT.md`) are for
  tickets 09 and 08.
