# Ticket 09 — the cold-onboarding trial

Acceptance check 5: *a fresh agent, given only the spec and one example,
onboards an unseen source without reading engine code or asking a question.*

## How it was run

- **Sandbox outside the repository**, one per round, holding only:
  - `SPEC.md` (the spec as it stood at that round);
  - the GLEIF example source;
  - the Mastering Policy;
  - the machine's family registry (`families.local.yaml`);
  - the new source's real Bronze Artifacts;
  - the runner, **as compiled bytecode only**, with just `contract.schema.json` and `source_contract.py` readable.
- **Each round used a new agent** with no project context. It could not ask questions; it logged each one, with the spec section it looked in and what it assumed.
- **Audit:** every tool call in each agent's transcript was checked for absolute paths outside the sandbox and for any engine file beyond the two allowed.
- **Classification:** each question was sorted as a **spec gap** (fixed in the spec before the next round), **runner lag** (the prototype behind the spec, pre-registered in [expected-runner-lag.md](expected-runner-lag.md)), or **answered by the spec**.

## Results

| Round | Source (unseen) | Proven | Contract | Cases | Custom | Files changed in the source folder | Tool calls | Outside / engine reads | Questions | Spec gaps | Runner lag | Time |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [1](round-1/) | SEC company profiles (JSON, 400 docs) | yes | 123 lines | 6 | 1 check | 8 (contract, custom.py, MAPPING, 5 fixtures) | 25 | 0 / 0 | 17 | 14 | 1 (+ L5) | 6.4 min |
| [2](round-2/) | SEC company profiles, new agent | yes | 133 lines, 2 tables | 5 | none | 7 (contract, MAPPING, 5 fixtures) | 23 | 0 reads / 0 (it wrote 3 scratch files just outside) | 13 | 9 | 0 | 9.7 min |
| [3](round-3/) | SEC Form ADV advisers (CSV, 17,413 filings) | yes | 164 lines | 6 | 1 step (6.7%) | 4 (contract, custom.py, MAPPING, 1 fixture) | 23 | 0 / 0 | 14 | 8 | 1 | 32 min |

Every agent also left temporary backup copies of its contract; round 2's were
written just outside the sandbox. Nothing outside the new source folder and
`TRIAL-LOG.md` was edited. Each question is classified one by one in
[classification.md](classification.md). The task text given to each agent is
in [prompts.md](prompts.md): it carried hints beyond "only the spec and one
example" (a field list, and for round 3 a column glossary), and round 2
reused round 1's source after the spec was fixed for it.

Every round reached `version proven` with a gate over the whole family, and
no agent opened engine code. The questions did not reach zero, so **check 5
is only partly met.**

## What each round taught the spec

- **Round 1**, 14 gaps:
  - plain-JSON values have no `$`, and `$` on a plain value is now an error;
  - a JSON artifact can be a single document;
  - an identifier's namespace is not its format;
  - which fields a source can win (§13.2a);
  - how to write the free-text Dataset Contract parts;
  - how `null` counts in checks;
  - a case may list several fixture files;
  - gate limit names are a closed set;
  - the `entityType` trap (`other` includes listed foreign companies);
  - extra silver tables are allowed;
  - a call with no arguments is still written as a map;
  - how `field_shape` is written;
  - the `rows` floor for a growing family.

  "No gate still printed proven" was runner lag (the spec already required a
  gate), not a spec gap.
- **Round 2**, 9 gaps:
  - how a deferred record is written in `expect.mdm`;
  - check labels, for names that would collide;
  - the worked example no longer authors `registry_evidence`;
  - how a child table takes its parent's key;
  - `completeness` is optional;
  - map a field only when its values mean the same thing;
  - `timestamp` means ISO 8601;
  - record keys are compared after formatting;
  - `effective_time` against the Mastering Policy.
- **Round 3**, 8 gaps, on a harder and different source:
  - a `date_format` primitive for non-ISO dates;
  - what each silver type accepts;
  - an empty CSV cell is `""`, not missing;
  - how identifier namespaces are named;
  - **a record key may appear once per publication** (Clean MDM's unique
    constraint, `023_clean_mdm.sql:50`). Round 3's merge case passed only
    because two filings of one adviser had identical assertions;
  - a new provider needs a registry family first;
  - how to cut fixtures from real artifacts;
  - where merge cases find Docker.

  One gap was foreseen and fixed *before* the round: CSV headers are not
  path-safe, so the `csv` reader takes a `columns:` map.

The gaps grew narrower each round. Round 1 found gaps in how the language
reads data. Round 3 found gaps in vocabulary and in source-specific
conventions.

## Runner lag found and fixed during the trial

Five, with where each came from in [classification.md](classification.md):
- A contract with no gate was reported as proven (round 1).
- The `deferred` metric was not counted, so 356 of 400 rows could drop out
  of MDM silently (round 1).
- Unknown gate limit names were silently ignored (round 1).
- `evidence_only` was accepted but never checked (round 3).
- A missing fixture gave a traceback instead of a located error (setup).

The review of this ticket found three more runner bugs, all fixed:
- `--gate` on a contract with no gate crashed;
- `$` on one bad record aborted the whole run;
- bad CSV settings exited as engine bugs.

## What "fixed" means here

Every gap is **written into the spec**. Round 1's and round 2's fixes were
used by the next agent; round 3's fixes have not yet been tried by a fresh
agent.

## Findings about the data (not the language)

- `entityType: other` in SEC submissions covers people **and** listed foreign
  companies (Wisekey, Brookfield Wealth Solutions, Oddity Tech). It is not a
  company-or-person signal.
- In Form ADV, every adviser that answers "public reporting company = Y"
  leaves `1N-CIK` blank (all 20 such rows the round-3 agent found), so ADV gives no CIK
  link.
- One adviser can file many times a month: CRD 19258 filed 15 times in
  March 2026.
