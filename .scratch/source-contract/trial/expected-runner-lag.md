# Ticket 09 — known spec-vs-runner divergences (written BEFORE the trial)

The trial agent follows `SPEC.md`. The runner it uses is the throwaway
prototype, which the spec's review deliberately made stricter or wider than.
If the agent hits one of the items below, it is **runner lag** (the prototype
is behind the spec), not a spec gap, and it does not become a spec fix. Any
other difficulty is scored as a **spec gap**.

| # | Spec says | Prototype runner does |
|---|---|---|
| L1 | JSON `null` is not missing; `default` applies to missing only (§8.3) | treats `null` as missing |
| L2 | `default` is required on `join` and `value_with_footnotes` (§9) | optional on both |
| L3 | Custom Steps are registered per source (§11) | one shared registry (harmless for one source per run) |
| L4 | `csv` reader (§8.1) | not implemented |
| L5 | `deferred` gate metric; `expect.mdm.evidence_only`; `collapse` (§12, §15, §16) | not implemented; the schema rejects `collapse` and `evidence_only` |
| L6 | `new`, `deferred`, `quarantined` merge outcomes (§15) | only `bound`, `binding_required`, field value/winner |
| L7 | readers yield documents one at a time (§8.1) | returns a list |
| L8 | `--all`, `source save`, `source export`, `source families` (§4.5, §10) | not implemented |
| L9 | plain YAML scalars read as text (§6) | keeps YAML numbers; dates become text |
| L10 | a missing fixture file should be a located failure (implied by §17) | engine traceback, exit 3 (seen while building the sandbox) |

Sandbox facts the agent is given (not spec content): the runner command
(`./source`), the family name `sec.submissions_company` and that it is
registered in `families.local.yaml`, and where the batch data sits.
