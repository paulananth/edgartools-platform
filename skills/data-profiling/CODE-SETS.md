# Reference data: a draft code set in RDM

Part of the `data-profiling` skill: [SKILL.md](SKILL.md) says when to read this.

## Reference data: a draft code set in RDM

A part classed reference data becomes a code set version in RDM
(`docs/specs/rdm/spec.md`). Agents draft; only the operator approves.

1. **Look first:** `edgar-warehouse rdm list`, then
   `edgar-warehouse rdm describe <code set>` for what a code set means, where
   its values live and how to compare them. A code set that already exists
   gets a new version that names the current one in `supersedes`, never a
   second code set.
2. **Write the draft file** (JSON or YAML) from the approved findings:
   `{code_set: {code_set, name, definition, authority, steward}, version,
   created_by, evidence, supersedes, codes, labels, levels, crosswalk}`.
   - `codes`: each code with its `label`. A reference hierarchy gives each
     code one `parent_code`. An invalid row stays, with `status: invalid` and
     its `invalid_reason`.
   - A value per period (a rate, a threshold): `value` (exact decimal text as
     published, never a float) with its `unit`, both or neither, on a child
     code dated to its period (`valid_from`, `valid_to`) under the code it
     belongs to; a consumer takes the child whose period holds its date.
   - Named properties: what a code's own words cannot say, as
     `properties` (each text, `true` or `false`, or a list of distinct texts;
     names in lower-case words joined by `_`). The Rust preparation checks
     them and the canonical form names them only on a code that has some, so
     a version without them keeps its pin. Example: a relationship type's
     ends and rules (`mdm-relationship-types`, data-onboarding REFERENCE.md).
   - `labels`: one `preferred` label per language, plus any `synonym`s.
   - `levels`: the names stewards gave each depth.
   - `crosswalk`: a code mapped to another code set, with `match_type`
     `exact`, `close`, `broad` or `narrow`. A standard RDM does not hold
     has `to_version: outside`.
   - `usage`: where the codes' values live (`store` mdm, silver, source or
     other; `object`; `field`) and how a value is compared (`exact` or
     `upper_trimmed`). Take it from the findings' columns that hold the codes.
   - `hints`: plain words for the next agent: `meaning`, `use_when`,
     `avoid_when`, `example_question`. Write only what the evidence shows.
   - `created_by`: the agent and this skill. `evidence`: an object (the store
     refuses text): the findings file, and the counts the codes rest on.
   - **A new version of a published code set** (a code added to a set the
     policy pins): `scripts/rdm_next_version.py <code set> <version> --add
     <codes.yaml> --out <draft file>` writes the draft from the published
     rows plus the added codes (each in the published row shape), and
     refuses when the published rows do not rebuild their pinned sha256 or an
     added code is already held. To diff and publish it in a disposable RDM,
     draft and publish the version it supersedes there first, from the same
     script with nothing added (its sha256 must equal its pin).
3. **Draft:** `edgar-warehouse rdm draft --file <draft file>`.
4. **Ask for approval.** Show the operator the draft and
   `edgar-warehouse rdm diff <code set> <current> <draft>`. Record their
   approval only in their words:
   `edgar-warehouse rdm approve <code set> <version> --by "<operator>" --words "<their exact words>"`.
5. **Publish:** `edgar-warehouse rdm publish <code set> <version> --out <folder>`.
   It writes `<folder>/<code set>/<version>/`. A repo code set keeps only
   `canonical.jsonl` and `pin.json` under `rules/reference/published/<code
   set>/<version>/`: publish to a scratch folder and copy those two, then check
   the canonical file's sha256 equals the pin. With no RDM database live, use a
   disposable PostgreSQL 16 with its own database named `rdm` (`rdm init`
   refuses another) and a runtime login, as the earlier code sets did.
   `pin.json` there holds `{code_set, version, sha256}`, which a consumer pins.

A table kept as a map of code to fields drafts with
`edgar-warehouse rdm import-reference <name> --label <field> --crosswalk <field>=<code set>@<version>:<match type>`.
Every field must find a place (the label or a crosswalk), and the draft must
rebuild the table exactly, or nothing is written.
