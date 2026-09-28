# Research 11: a format for the Mapping Document and the data catalog

Ticket: [11](../issues/11-init-mode-mapping-document-and-catalog.md). Written 2026-09-28 (ET).
Sources: the standards' own repositories, specifications and vendor documentation,
each cited by URL where it is used; this repository at branch
`claude/rules-11-mapping-document`. **Zero requests to sec.gov.**

Everything under "Recommendation" is a recommendation for the operator, **not a
decision**.

## Answer first

1. **Keep the YAML rules as the only thing that runs, and make the Mapping
   Document a generated Markdown view of them that stewards may edit.** A
   steward's edit is a request. The agent turns it into a change to the YAML
   and regenerates the document; the steward confirms the regenerated rows say
   what they meant. A check in CI regenerates every document and refuses any
   difference from the committed one. No parser for Markdown is needed. For a
   new source, init mode prints the document from the agent's unsaved working
   draft, and nothing is saved as a rule until the document is agreed.
2. **No published standard fits the whole job.** ODCS (the Open Data Contract
   Standard) is the closest for the per-source part: it has a
   `criticalDataElement` flag, source-to-target transform fields and data
   quality rules. It has **no match, merge or survivorship concept**, and it
   would be a third YAML shape to keep in step with ours. Borrow its words; do
   not adopt it as storage.
3. **Every MDM product surveyed shows stewards the same two things we need**:
   an ordered list of preferred sources per field (Semarchy "Preferred
   Publisher", Reltio `SRC_SYS`, Tamr dataset priority groups, Informatica
   trust scores) and a list of named matching rules. Our document should show
   exactly those, in those words.
4. **Spreadsheets fail the git test.** A source-to-target mapping (STTM)
   spreadsheet is what stewards know best, but `.xlsx` is a binary file that a
   pull request cannot show line by line, and STTM has no owning standard.
5. **Steward notes belong in the Markdown, not the YAML.** YAML comments are
   thrown away by definition, and a note inside the YAML would change the
   rules' digest and need a new approval for a typo.
6. **The data catalog is generated only**: one `rules/CATALOG.md` listing every
   source, every dataset (source code), every MDM kind and field, and which
   sources fill each field in which order. Stewards edit per-source documents,
   never the catalog.

## 1. What the document must hold, and where each part lives today

The operator's ruling (2026-09-28, [ticket 11](../issues/11-init-mode-mapping-document-and-catalog.md))
lists five things per source. Each already has one home in the rules files.
A format is only sustainable if every row of the document points at exactly
one place in the YAML.

| Document part | Where it lives in the rules | Can a steward change it in place? |
|---|---|---|
| Source field → MDM field | `mdm.<code>.contract.adapter.fields` in `source.yaml`, including nested `address.components` ([sec.submissions.company](../../../rules/sources/sec.submissions.company/source.yaml)) | Yes: a new source version, saved, proved and approved |
| Identifiers | `adapter.identifiers`, `identifier_formats`, `record_key`, `record_key_format` | **No.** SKILL.md refuses these changes within one source code; they need a new code (`….v2`) ([skills/rules/SKILL.md](../../../skills/rules/SKILL.md), "Hard rules"). The document must say so on those rows |
| Critical data element | A check in `quality.yaml` with `test: present@1` and `on_fail: exception` ([quality.yaml](../../../rules/sources/sec.submissions.company/quality.yaml), `name_present`). There is no separate flag | Yes, but "critical: yes" means *adding a check*, and "no" means *removing one* |
| Data quality checks and fixes | `quality.yaml`: `fixes` then `checks`, each `id`, primitive, `args`, `on_fail` (`exception`, `withhold`, `flag`) | Yes for `on_fail` and simple lists; long argument lists (e.g. the 12 registered-agent markers) stay in YAML |
| Merge priority: which source wins each MDM field | `defaults.sources` in `rules/merge/kinds/<kind>.yaml` (Company: SEC first, then GLEIF), with per-field rules under a `fields` section when a kind has one ([survivorship.py](../../../edgar_warehouse/mdm/clean/survivorship.py) `_rules_for`, `_defaults_for`) | **Only in the kind's document.** The spec makes ranking a source a separate Mastering Policy change with its own approval, because it moves other sources' winners ([spec §13.2a](../../../docs/specs/source-contract/spec.md)). A source's document shows it read-only |
| Matching rules, in order | `rules` in the kind file: `family: classification` (ordered steps) and `family: name_binding` rules | Only in the kind's document, as above |

**What "in order" means, checked in code.**
- Classification steps are **first match wins**: "A rule is an ordered list of
  steps. The first step whose `when` list holds…"
  ([classification.py](../../../edgar_warehouse/mdm/clean/classification.py), module docstring). Reordering
  steps changes outcomes.
- Name-binding rules run in file order ([matching.py](../../../edgar_warehouse/mdm/clean/matching.py)
  `active_rules`, `propose`). A GLEIF record already bound, including by an
  earlier rule in the same batch, is skipped by later rules ("already joined;
  a name match never re-binds"). Both current rules bind a GLEIF record to the
  one Company its SEC holder already holds, so for these two rules the order
  decides **which rule is credited**, not which Company is chosen. It can also
  change which reviews are recorded: an ambiguity review raised under the first
  rule does not stop the second from binding. (Read in code, not run.) The
  document should say "rules are tried in this order; the first that binds
  records the decision", not suggest that reordering changes the Company.

**Sources without a `read` section.** The live sources (`sec.submissions.company`,
`gleif`) keep parsing in existing code, so their "source field" is the parser's
output column (`entity_name`, `business_address.street`), not a path in the
captured file. The Source Contract spec's Mapping Document column set
([§20](../../../docs/specs/source-contract/spec.md): silver column, bronze path, MDM target) was written for
contracts with a `read` section, as in the prototype's
[gleif MAPPING.md](../../source-contract/prototype/sources/gleif/MAPPING.md). For today's sources the
"From the captured file" column must name the parser instead
(`parsed by gleif_source.py`), and say so plainly.

**MDM field definitions have no home today.** The catalog can list MDM fields as
the union of every source's `adapter.fields`, but nothing in `rules/` holds a
field's meaning ("`name`: the legal name as the source writes it"). This is
**open**; see "Open questions".

## 2. The candidates

Each is judged on the five questions the task set. "Round trip" means: can our
YAML be turned into this format and back with nothing lost?

### 2.1 Open Data Contract Standard (ODCS), Bitol

- **What it is.** A YAML data contract: "This document describes the keys and
  values expected in a YAML data contract"
  ([ODCS docs](https://github.com/bitol-io/open-data-contract-standard/blob/main/docs/README.md)). Latest release v3.2.0,
  2026-09-08 ([releases](https://github.com/bitol-io/open-data-contract-standard/releases)).
- **Fields that match our needs.** Each schema property can carry
  `criticalDataElement` ("If element is considered a critical data element
  (CDE) then true else false"), `primaryKey`, `transformSourceObjects`,
  `transformLogic`, `transformDescription`, `businessName` and `examples`
  ([schema.md](https://github.com/bitol-io/open-data-contract-standard/blob/main/docs/schema.md)). Quality rules are
  `type: library | text | sql | custom`, with a `metric` such as `nullValues`,
  a `dimension` (`accuracy`, `completeness`, `conformity`, `consistency`,
  `coverage`, `timeliness`, `uniqueness`) and a free `severity`
  ([data-quality.md](https://github.com/bitol-io/open-data-contract-standard/blob/main/docs/data-quality.md)).
  Anything else goes in `customProperties`
  ([custom-other-properties.md](https://github.com/bitol-io/open-data-contract-standard/blob/main/docs/custom-other-properties.md)).
- **What it lacks.** No concept of source priority, survivorship, matching,
  identity kind or exception-versus-withhold. Our whole merge half would sit in
  `customProperties`, which no ODCS tool understands.
- **Human-editable:** as much as any YAML; more verbose than ours (a property
  is a list item with ~20 optional keys).
- **Round trip:** possible for the mapping and quality parts with a converter we
  would write and maintain; lossy for our primitives (`registered_agent_address@1`
  has no library metric, so it becomes `type: custom`, an unparsed string).
  Not verified by building one.
- **Diffable:** yes, text.
- **Tools:** the Data Contract CLI lints, tests, prints changelogs and breaking
  changes, and exports HTML, Markdown and Excel
  ([datacontract-cli README](https://github.com/datacontract/datacontract-cli/blob/main/README.md)).
- **Governance:** Bitol is "a Linux Foundation AI & Data Incubation project
  licensed under the Apache 2.0 license", run by a Technical Steering
  Committee ([bitol.io](https://bitol.io/)). "In case of conflict between the
  standard and the JSON Schema, the standard takes precedence"
  ([ODCS docs](https://github.com/bitol-io/open-data-contract-standard/blob/main/docs/README.md)). Stable
  and actively governed.

### 2.2 Data Contract Specification (datacontract.com)

- **Deprecated.** "With the release of the Open Data Contract Standard v3.1.0,
  we deprecate the Data Contract Specification … supported in Data Contract CLI
  and Entropy Data until the end of 2026"
  ([datacontract-specification README](https://github.com/datacontract/datacontract-specification/blob/main/README.md)).
  Do not start on it. The same CLI now "natively supports the Open Data
  Contract Standard" ([datacontract-cli README](https://github.com/datacontract/datacontract-cli/blob/main/README.md)).
- **Editable / round trip / diffable / tools:** as ODCS; moot given the notice.

### 2.3 dbt properties files (`schema.yml`) and dbt docs

- **What it is.** YAML descriptions for models, sources and columns; Markdown is
  allowed, and long text can live in `{% docs %}` blocks in `.md` files
  ([dbt description](https://docs.getdbt.com/reference/resource-properties/description)). `meta` "accepts any
  key-value pairs … compiled into the `manifest.json` … and is visible in the
  auto-generated documentation" ([dbt meta](https://docs.getdbt.com/reference/resource-configs/meta)).
- **Fit.** The pattern is the useful part: **structured facts in YAML, prose in
  Markdown files beside it, one generated site.** It describes tables that dbt
  builds; it has no source-to-MDM mapping or survivorship concept.
- **Human-editable:** yes. **Round trip:** not applicable; it would be a second
  copy of our facts. **Diffable:** yes. **Tools:** dbt, already in this repo for
  gold. **Governance:** a vendor's product format (dbt Labs), versioned with dbt.

### 2.4 Frictionless Table Schema / Data Package

- **What it is.** "A simple language- and implementation-agnostic way to
  declare a schema for tabular data", v2, JSON; fields have `name`, `title`,
  `description`, `type`, `constraints` (`required`, `unique`, `enum`,
  `pattern`…), plus `primaryKey`, `foreignKeys`, `missingValues`; a field "MAY
  contain any number of other properties"
  ([Table Schema v2](https://datapackage.org/standard/table-schema/)). Maintained by the Data Package
  Working Group (Open Knowledge Foundation's Frictionless Data).
- **Fit.** Good for describing one table's columns; nothing on mapping between
  datasets, critical elements or merging. `missingValues` is the same idea as
  our `none_values` proposal (research 09).
- **Human-editable:** JSON, less so than YAML. **Round trip:** only the column
  list. **Diffable:** yes. **Tools:** Frictionless validators. **Governance:**
  open working group, stable (v2).

### 2.5 OpenMetadata and DataHub: glossary and lineage models

- **OpenMetadata.** A glossary term has `synonyms`, `relatedTerms`,
  `reviewers`, `owners` and an `entityStatus` of `Draft`, `In Review`,
  `Approved`, `Archived`, `Deprecated`, `Rejected`, `Unprocessed`
  ([glossaryTerm.json](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/entity/data/glossaryTerm.json),
  [status.json](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/type/status.json)).
  Column lineage is `fromColumns`, `toColumn` and a `function`
  ([entityLineage.json](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json)).
- **DataHub.** A business glossary can be loaded from a YAML file (`nodes`,
  `terms`, each with `name`, `id`, `description`, `owners`, `term_source`,
  `inherits`, `contains`, `custom_properties`)
  ([business-glossary source docs](https://github.com/datahub-project/datahub/tree/master/metadata-ingestion/docs/sources/business-glossary)).
  Column lineage is `FineGrainedLineage`: `upstreams`, `downstreams`,
  `transformOperation`, `confidenceScore`
  ([FineGrainedLineage.pdl](https://github.com/datahub-project/datahub/blob/master/metadata-models/src/main/pegasus/com/linkedin/dataset/FineGrainedLineage.pdl)).
- **Fit.** These are **catalog servers**: the store of record is their database,
  edited in their UI; DataHub's glossary YAML is an ingestion input, not a
  round-trippable export. Running one is far more machinery than this project
  wants. Their approval states are also not our Rule Activation Approval.
- **Human-editable:** in the UI, yes. **Round trip:** no (server is master).
  **Diffable:** only the DataHub glossary YAML. **Tools:** large. **Governance:**
  open-source products, Apache-2.0 (OpenMetadata 2.0.2, 2026-09-16; DataHub
  v1.7.0.1, 2026-09-03; from each repository's releases). Useful later, as a
  place to *publish* the generated catalog, not to author rules.

### 2.6 OpenLineage column lineage

- **What it is.** "An Open standard for metadata and lineage collection
  designed to instrument jobs as they are running"; an LF AI & Data Graduate
  project ([OpenLineage README](https://github.com/OpenLineage/OpenLineage/blob/main/README.md)). Its column
  facet maps each output field to `inputFields` (`namespace`, `name`, `field`)
  with `transformations` of type `DIRECT` or `INDIRECT`
  ([ColumnLineageDatasetFacet.json](https://github.com/OpenLineage/OpenLineage/blob/main/spec/facets/ColumnLineageDatasetFacet.json)).
- **Fit.** It records what a run *did*; it is emitted by jobs, not written by
  people. Not an authoring format. Its DIRECT/INDIRECT split is a good word for
  "mapped" versus "used only to decide" (our `matching` block).
- **Human-editable:** no (events). **Round trip:** not applicable.
  **Diffable:** not applicable. **Governance:** stable, Apache-2.0.

### 2.7 Classic source-to-target mapping (STTM) spreadsheets

- **No owning standard.** There is no specification body for STTM; each team
  invents its columns. The nearest governed form is ODCS's own transform
  fields (2.1) and the Data Contract CLI's Excel template, which it can
  `import excel` and `export excel` ([datacontract-cli README](https://github.com/datacontract/datacontract-cli/blob/main/README.md),
  [excel_importer.py](https://github.com/datacontract/datacontract-cli/blob/main/datacontract/imports/excel_importer.py)).
  Whether that Excel round trip is lossless was **not verified**.
- **Human-editable:** the most familiar format for stewards. **Round trip:**
  only through a tool like the one above. **Diffable:** **no**: `.xlsx` is a
  binary zip; git can only diff it through a configured text converter
  ([gitattributes, "Performing text diffs of binary files"](https://git-scm.com/docs/gitattributes)).
  A CSV is diffable and GitHub renders it as a table ("any .csv or .tsv file …
  automatically renders as an interactive table"
  ([GitHub docs](https://docs.github.com/en/repositories/working-with-files/using-files/working-with-non-code-files))),
  but a CSV has no place for headings, notes or the merge section.

### 2.8 Great Expectations and Soda (check formats)

- **Great Expectations (GX Core 1.x).** Expectation suites are objects with
  `meta` and `notes`, serialised to JSON
  ([expectation_suite.py](https://github.com/great-expectations/great_expectations/blob/develop/great_expectations/core/expectation_suite.py));
  "Data Docs translate Expectations, Validation Results, and other metadata
  into human-readable documentation that is saved as static web pages"
  ([GX Data Docs](https://docs.greatexpectations.io/docs/core/configure_project_settings/configure_data_docs/)).
  Apache-2.0. The lesson again: **the readable page is generated from the checks**.
- **Soda Core v4.** Contracts in "a clean, human-readable YAML syntax":
  `dataset`, `checks`, `columns[].checks` (`missing`, `invalid` with
  `valid_values`, thresholds) ([soda-core README](https://github.com/sodadata/soda-core/blob/main/README.md)).
  **Licence: Elastic License 2.0** ([LICENSE](https://github.com/sodadata/soda-core/blob/main/LICENSE)).
- **Fit.** Both describe checks on a table, not per-record checks that decide
  whether a record may merge. Our `on_fail: exception | withhold | flag` has no
  equivalent in either. Human-editable: yes (Soda YAML), less so (GX JSON).
  Round trip: not with our primitives. Diffable: yes. Neither is needed.

### 2.9 How MDM products show match, merge and survivorship to stewards

- **Informatica MDM (Multidomain 10.x, on-premises docs).** Each column from
  each source has a trust level "between 0 and 100"; trust decays over time,
  and validation rules downgrade it "by the percentage specified in the
  validation rule" ([Trust Settings](https://docs.informatica.com/master-data-management/multidomain-mdm/10-4-hotfix-1/configuration-guide/part-4--configuring-the-data-flow/mdm-hub-processes/load-process/trust-settings-and-validation-rules/trust-settings.html),
  [Validation Rules](https://docs.informatica.com/master-data-management/multidomain-mdm/10-4/configuration-guide/part-4--configuring-the-data-flow/mdm-hub-processes/load-process/trust-settings-and-validation-rules/validation-rules.html)).
  Configuration is exported as change-list XML that "can be subsequently
  reviewed, edited, and applied", archived or "stored in a source control
  system" ([Change List XML Files](https://docs.informatica.com/master-data-management/multidomain-mdm/10-4-hotfix-2/repository-manager-guide/introduction/metadata-management-concepts/change-lists/change-list-xml-files.html)).
  These are 10.x on-prem pages; the current cloud product was not checked.
- **Reltio.** Survivorship strategies per attribute, including `LUD` (last
  update, the default), `SRC_SYS` (a priority list of sources), `Frequency`,
  `Aggregation`, `OldestValue`; configured "via the Hub or via the
  Configuration API" as JSON
  ([Survivorship Rules](https://docs.reltio.com/en/model/consolidate-data/design-survivorship-rules/survivorship-rules)).
  Match rules are `matchGroups`, each with a `type` of `automatic` (merge),
  `suspect` (queue for review) or `relevance_based` (a score)
  ([Match Groups](https://docs.reltio.com/en/reltio/what-does-reltio-do/what-reltio-does-at-a-glance/data-unification-and-mdm-at-a-glance/data-unification-and-mdm-in-detail/reltio-match-and-merge/the-match-groups-construct)).
- **Semarchy xDM.** A survivorship rule is "a consolidation rule" plus "an
  override rule"; strategies include Custom Ranking, Most Frequent Value and
  Preferred Publisher ("Publishers are manually ordered. The first one
  returning a value for the field is used")
  ([Survivorship](https://www.semarchy.com/doc/semarchy-xdm/xdm/5.3/Design/matching/survivorship.html)).
  Match rules are SemQL conditions with a confidence score; "the merge policy
  … defines the confidence score thresholds required for automatic merging"
  ([Match and merge](https://www.semarchy.com/doc/semarchy-xdm/xdm/5.3/Design/matching/matching.html)).
- **Tamr.** Golden-record rules such as Most Common Value, Max, Min, Longest,
  with dataset priority groups: "it considers the datasets in the highest
  priority group first"
  ([Golden Record Consolidation Rules](https://docs.tamr.com/new/docs/golden-record-consolidation-rules)).
  Matching is learned: curators label pairs "Match or No Match" to train a
  model ([Mastering Projects](https://docs.tamr.com/new/docs/overall-workflow-mastering),
  [Training Initial Pairs](https://docs.tamr.com/new/docs/training-initial-pairs)).
- **What they share.** All four keep rules in a proprietary store edited through
  a UI; none offers a portable, human-edited text file as the master. What
  stewards are shown is consistent: **per field, an ordered list of preferred
  sources**, and **named match rules with what each does** (merge, send to
  review). Our kind file already holds both; the document should present them
  in those terms: "Preferred sources, in order" and "Matching rules, tried in
  order: what each checks, what it does (bind, wait)". Our rules are
  deterministic and measured, so the Tamr-style learned model does not apply.

### 2.10 The formats side by side

| Format | Stewards can edit | Round trip with our YAML | Diffable in a PR | Tools | Standard's stability |
|---|---|---|---|---|---|
| ODCS | YAML, verbose | Partial, lossy for merge rules and our primitives; converter to write (not verified) | Yes | Data Contract CLI | LF AI & Data incubation, TSC, v3.2.0 |
| Data Contract Spec | YAML | As ODCS | Yes | Same CLI until end 2026 | **Deprecated** |
| dbt `schema.yml` + docs | Yes | Not applicable (a second copy) | Yes | dbt | Vendor format |
| Frictionless Table Schema | JSON | Column list only | Yes | Frictionless | Working group, v2 |
| OpenMetadata / DataHub | UI | No (server is master) | DataHub glossary YAML only | Heavy servers | Apache-2.0 products |
| OpenLineage | No (events) | Not applicable | Not applicable | Marquez etc. | LF AI & Data Graduate |
| STTM spreadsheet | Best known to stewards | Only via a tool (not verified) | **No** for `.xlsx`; yes for CSV | Excel | No standard |
| Great Expectations | JSON | No | Yes | GX | Apache-2.0 product |
| Soda Core | YAML | No | Yes | Soda | Elastic License 2.0 |
| Vendor MDM configs | UI | No | Informatica XML only | Vendor | Proprietary |
| **Generated Markdown (this note)** | Yes: tables and headings | **Exact by construction**: regenerate and compare | Yes, with rendered rich diff ([GitHub docs](https://docs.github.com/en/repositories/working-with-files/using-files/working-with-non-code-files)) | Our generator plus GitHub | Ours; GFM tables ([GFM spec](https://github.github.com/gfm/#tables-extension-)) |

## 3. Two constraints that decide the shape

**YAML comments cannot hold decisions.** The YAML 1.2 specification: "Comments
are a presentation detail and must not be used to convey content information"
([YAML 1.2.2](https://yaml.org/spec/1.2.2/)). Our loader and `rules migrate
--to-files` already lose them ([files.py](../../../edgar_warehouse/rules/files.py); SKILL.md: "`--to-files` writes them back,
without their comments, and the comments hold decisions"). Today the
operator's reasons live in those comments. Putting them in the Markdown
document, which is kept in git and never exported from the database, gives
them a durable home.

**Notes should not go into the YAML either.** The deciding reason: a note in
the YAML changes the digest, so fixing a typo in a note would need a new
approval. There are also mechanical limits. The spec proposes a `why:` field
for reasons that must survive storage ([spec §6](../../../docs/specs/source-contract/spec.md)), but no rules file uses
one. A kind file with an undeclared top-level section is refused
([survivorship.py](../../../edgar_warehouse/mdm/clean/survivorship.py) `_kind_authority`: "A kind section must be declared
authority-bearing or not"). A quality block refuses keys other than
`version`, `fixes` and `checks` at its top level
([quality.py](../../../edgar_warehouse/mdm/clean/quality.py) `check_quality`), though it does not check extra keys on a
single fix or check, so a `why:` there would probably load (not tried). Notes
therefore live in the Markdown only.

**Markdown tables have limits.** "Block-level elements cannot be inserted in a
table", and a `|` in a cell must be escaped ([GFM spec](https://github.github.com/gfm/#tables-extension-)).
So long lists (the 100-entry `company_legal_form` list, the 12 agent markers)
appear as a count and a link to the YAML, not in a cell. Classification steps
appear as one plain-English line each.

## 4. The precedence question

`CONTEXT.md` defines the Mapping Document as generated and warns against "a
hand-written mapping spreadsheet, a document that can drift from what runs"
([CONTEXT.md](../../../CONTEXT.md), "Mapping Document"); the spec says `MAPPING.md` is "generated; never
edited by hand" ([spec §5, §20](../../../docs/specs/source-contract/spec.md)). The operator's later ruling
(2026-09-28 09:57 ET, [ticket 11](../issues/11-init-mode-mapping-document-and-catalog.md)) says the generated
document "must be able to edit and update by stewards". Under SKILL.md, "the
later operator decision wins". The recommendation below keeps both intents:
stewards edit it, and it still cannot drift, because a check refuses any
difference between the document and what the rules generate. Follow-ups (not
made here): update `CONTEXT.md`'s Mapping Document entry and spec §5 and §20.

## Recommendation

**The format.** Generated GitHub-flavoured Markdown, one file per source and
one per kind, plus one generated catalog. The facts are tables whose every row
names one YAML path. Steward prose lives in marked regions the generator keeps.

**Where it lives.**
- `rules/sources/<source>/MAPPING.md`, beside `source.yaml` and `quality.yaml`.
  Sections: the source and its datasets; **Fields** (source field or parser
  column → MDM field, or "evidence only", or "used for matching only");
  **Identifiers** (marked "changing this needs a new source code");
  **Critical data elements** (fields whose absence makes the record an
  exception, from `present@1` + `on_fail: exception` checks); **Data quality**
  (each fix and check: what it does in one line, what happens on failure);
  **Who wins each field** (read-only, copied from the kind: "SEC first, then
  GLEIF"; "evidence only: not ranked").
- `rules/merge/kinds/<kind>.md`, beside `<kind>.yaml`: **Preferred sources,
  in order** (the default and any per-field exception) and **Matching rules,
  tried in order** (classification steps as first-match lines; name-binding
  rules with what each checks and what it does). The binding order is
  described truthfully (section 1).
- `rules/CATALOG.md`: every source, every dataset (source code) with its kind,
  every MDM kind and field with the sources that fill it in priority order.
  Generated only. MDM field definitions are open (below).

**Generated versus edited.**
- Generated, and edited by stewards only as a request: every table.
- Owned by stewards and kept verbatim by the generator: text between
  `<!-- steward notes -->` and `<!-- end steward notes -->` markers, one region
  per section, plus a "Decisions" list (who decided, when, why). The operator's
  reasons now in YAML comments move here on first generation.

**Init mode (a new source).** The ruling says init first generates the
document from the captured files, and the rules follow from it.
1. The agent profiles the captured files and writes a *working draft* of
   `source.yaml` and `quality.yaml` (SKILL.md steps 3-7). Nothing is saved to
   the Rules Database.
2. It generates `MAPPING.md` from that draft, with the questions it could not
   answer marked in the notes regions. Stewards edit it (next list).
3. The loop repeats until the stewards and the operator agree the document.
   Only then does `rules save` store a draft version.

This honours "the rules follow from the document": no rule exists as a saved,
proven or approved version until the document is agreed. Until then the draft
YAML is only the agent's working copy, the thing the document is printed from.

**How a steward's edit becomes rules.**
1. The steward edits `MAPPING.md` in a branch and opens a pull request (for
   example, marks `country` critical, or changes `address` from evidence to
   field).
2. The agent reads the diff, changes the YAML to match (a new `quality.yaml`
   check, a new `adapter.fields` entry), and runs the Rules skill's dry run
   (step 8) with counts and examples of what the change does.
3. The agent then **overwrites the tables with the regenerated output**, so the
   generator, not the steward, owns the final wording of every row. The
   steward confirms in the pull request that the regenerated rows say what
   they meant. The check (below) then passes by construction. If the agent
   could not express the edit (an identifier change, a new primitive), it says
   why in plain words and the row stays as the rules have it.
4. `rules save`, `record-proof`, then the operator runs `rules approve` with
   the digest under their own login, after the agent has said in plain words
   what the digest is and what it changes. **The agent never approves.** A
   ranking or matching-rule change goes through the kind's document and is a
   separate Mastering Policy approval ([spec §4.3, §13.2a](../../../docs/specs/source-contract/spec.md)).
5. **Merging the pull request is not a Rule Activation Approval.** Git review
   records that the document and the files agree; only `rules approve` on the
   exact digest lets a version act.

**How drift is prevented.** One test, the same shape as
[`tests/unit/test_silver_schema_snapshot.py`](../../../tests/unit/test_silver_schema_snapshot.py) (one maintained
artifact held equal to another): for every source and kind, generate the
document from the YAML and compare it with the committed `MAPPING.md` and
`<kind>.md`, ignoring only the steward-notes regions; do the same for
`CATALOG.md`. A difference fails CI. A stale document and an unapplied steward
edit look the same to the test, and both must be resolved before merge: the
agent applies the edit to the YAML and regenerates, or regenerates to discard
it. Add a
`rules mapdoc <source> [--check]` command for the same comparison locally (the
spec already names `source mapdoc`, [§4.5](../../../docs/specs/source-contract/spec.md)).

**What not to adopt.** No ODCS storage, no spreadsheet, no catalog server.
Borrow words stewards may already know: "critical data element" (ODCS),
ODCS's quality dimensions as an optional label per check, "preferred sources"
(Semarchy's Preferred Publisher), and "direct" versus "used to decide"
(OpenLineage). If a catalog tool is wanted later, export `CATALOG.md`'s facts
to it one way; the rules stay the master.

## Open questions for the operator

1. **MDM field definitions.** Nothing in `rules/` says what an MDM field means.
   Options: a steward-notes region per field in `<kind>.md` (no digest change),
   or a new, approved section in the kind file. Recommended: the notes region.
2. **Catalog scope.** Sources, datasets and MDM fields only (recommended, per
   the ruling), or silver and gold too (ticket 11, "Open").
3. **May a steward's pull request change a kind's document**, or only the
   operator's? Ranking a source moves other sources' winners.
4. **Moving today's YAML comments into the documents' notes regions** on first
   generation, so that `rules migrate --to-files` no longer loses decisions.
