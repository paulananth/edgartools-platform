# map: write the Dataset Contract

Part of the `data-onboarding` skill: [SKILL.md](SKILL.md) says when to read this.

### map: write the Dataset Contract

**Research first.** Start from "The source" in the log (**discover**, "Know the
source first"); read here only what it left out. If a document named here is
missing, go on and log it.
- `CONTEXT.md`: the words MDM uses.
- What MDM and RDM already hold: `edgar-warehouse context <kind|relationship|code set> <key|--search words>`
  (read only, at most 8 KB; [REFERENCE.md](REFERENCE.md), "Reading MDM's context").
  Check a kind's existing records, a relationship type's links, or a code set's
  codes before you map onto them.
- `docs/specs/mdm/`: start with `source-evidence.md` and the policy
  spec of the kind you map onto.
- MDM kinds: `KINDS` in `edgar_warehouse/mdm/evidence.py`.
- **Declare the entity type first** (step 0 of mastering). Every Dataset Contract states where its records' entity
  type comes from, in `adapter`: `kind` when the source states one type, `classification` when a measured rule
  decides it, or `kind_field` with `kind_values` when the source's own category field does. A record whose type cannot
  be decided is set aside, never mastered. `rules check` refuses a contract that states none; the Mapping Document's
  `kind` row on the Source sheet shows each contract's entity type, and `edgar-warehouse rules entity-types`
  lists it per saved source version, the same on every database.
- The fields MDM keeps for a kind: `edgar-warehouse context <kind> --search`
  shows a live record's fields; the kind's field list in code, or, for a kind
  with none, its consumer spec's projection. Use these names; a new field is
  a question for the operator.
- `rules/merge/kinds/<kind>.yaml`. It ranks sources per kind
  (`defaults.sources`: the first one listed wins each field), and its
  comments record which value fills a shared field. Read them before you
  ask about a shared field. A new source of a kind that has others: rank
  them all with data-profiling's `rank_sources.py` ("Rank several sources")
  and propose the place it measures, not the end of the list by default.
- **Configured source extract.** Inspect the source's `read:` block and
  [READING.md](../data-platform/READING.md). Define the records passed to its
  Dataset Contract explicitly. For complete JSON evidence, `value: {path: .}`
  preserves the object in a named column; `mdm.prepare` selects that column
  with `record_column`. For projected rows, map from the configured columns.
  Retained source readers are comparison oracles during retirement: compare
  types, rows, refusals, assertion identities and provenance against them.
  What is still unfinished for each live source is in its ticket, not here;
  a raw projection does not qualify a full pipeline.
- The source's public documentation on the web: field definitions,
  identifiers, how often it publishes, full files or changes only.
  Third-party pages are hints, not authority. When the provider is ruled out
  (Examples), use the repo instead: the existing contract and its comments,
  `docs/specs/`, the published code sets in `rules/reference/published/` and
  the parsers.

**Infer, for each record type:**
- **Kind:** from `KINDS`, or the field or rule that decides it.
- **Record key:** its parts, in the order the source defines its unique key.
  The order is part of each record's identity.
  - **No publication time in a record key.** A delivery's date belongs in its
    publication, not the key, or each delivery makes a new record of the same
    entity (operator, 2026-10-22: "Fix 5"). A feed that restates its records
    in every delivery gives each delivery its own `publication_key` and a
    rising `revision` (its period, for example YYYYMM) in `mdm.prepare`, with
    `effective_at` its period end; a restatement left at revision 1 is
    refused ("contradictory publications").
  - A one-part record key is the plain value, not a one-item list: a test
    computes its subject from the value itself.
- **Identifiers:** each namespace and its format.
  - Ask about every identifier the source carries; never drop one silently.
  - An identifier with no format yet is declared, not coded: write
    `rules/identifiers/<name>.yaml` from its profiling finding
    ([REFERENCE.md](REFERENCE.md), "Identifier types").
  - Recommend keeping a cross-reference identifier as lookup-only, under its
    own name (operator, 2026-09-26): map it under `cross_references`
    ([REFERENCE.md](REFERENCE.md)).
  - Only an identifier a binding rule matches on joins two records into one;
    a name joins only through a proven name rule (operator, 2026-10-08:
    "Proven name rules may bind"), and a name id stays lookup only. Adding a
    joining identifier is a merge-rule change for the operator.
  - An identifier another authority issues is named for who stated it
    (`<stating source>_<id>`), never for the issuer.
  - A flag, role or type the source states about a record is evidence for a
    rule, never a key and never a decider on its own: such fields are often
    wrong or partial for the very records that matter.
- **Every master field reaches MDM.** Before **test**, list each master field
  the findings name (and each fact every row repeats about the master) and
  check it is in the kind's fields and the Dataset Contract, and that no
  silver table spec carries it (a link's source key excepted); one found in
  silver is a defect, not a choice (six master fields were once found in
  silver only, ruled for MDM three days before).
- **Fields:** use the kind's names. A list-shaped field has no contract
  syntax yet: leave it out, say so, and log a ticket.
  - **A date that usually changes stays out of MDM** unless it adds meaning
    to the entity or switches it on or off (operator, 2026-10-22: "date that
    changes usually should not be in MDM unless it adds meaning to the entity
    or turn on or off"). A source's record-keeping dates (last updated, next
    renewal) change the master's version without changing the entity: keep
    them in silver, or as the record's own effective time. A creation date, or
    a status change with its date, stays.
  - **Evidence about a link stays on the silver row**, not on the master: the
    issuer's identifier a holding names is the holding's, while the held
    entity reaches its issuer by the link (operator, 2026-10-22: "Fix 1").
- **Relationships:** type, the other end's key, the source it lives in,
  start and end. List every type the source carries. Label each mapped one's
  `scope` `<Provider> <relationship family>`.
  - **Only a link that describes the entities is an MDM relationship**: a
    parent, an issuer, a role, a fund's adviser, which change rarely. A
    position or an event (a holding, a transaction), restated in every report
    with its amount, is a silver row carrying the MDM ids of both ends and
    its as-of date, the date it holds at, beside the date it was reported (operator,
    2026-10-22: "Agreed Remove HOLDS from MDM's relationship types", "Don't
    we need a as of date for holdings").
    When a source states two report dates, tell them apart by their values
    before choosing: the as-of date falls just before the delivery, while a
    period end such as a fiscal year end often lies after it. Count the
    values that fall outside the delivery's window; they are why each row
    keeps its own date.
  - A link that states no start takes the time its record was first seen,
    so the record must carry one. Give the adapter `effective_at` naming the
    field that dates it (the month end of its file, a report date); without it
    every such link waits as `unknown_relationship_start`. Count the waiting
    links after the first load of a real file, not only in a test.
  - A relationship ends only on an end the source states. A record missing
    from a later file, or a source that falls silent, closes nothing.
  - Order and compare by the date the event happened, never the date it was
    reported: a late report is not a conflict.
  - A name can state a relationship ("A Series of <trust>", "<name> dba
    <name>", "Trustee", "ET AL"). Count each such wording in the files and
    bring it to the operator as a proposed link, in the same onboarding as
    the entities (relationships come with MDM). Until ruled, the name stays
    as written; never cut it into two entities by hand.
- **Evidence not captured:** when a rule needs evidence the capture does not
  hold yet, the record waits (set aside, with the reason) and the capture is
  a task. Never decide from the row alone.
- **A value of another kind** (an identifier of a different kind of entity)
  stays out of this kind; log it for that kind.
- **Provenance:** trace stays beside the record (operator, 2026-09-27).
  Capture hashes, run ids and sync times never go into `provenance`. Only
  the source's own record may, when the reader keeps it (`native_record`).
- **An unmapped source value:** first test whether configured `value`, paths,
  iteration or frozen references can preserve it. Map only evidence the
  tested source extract emits. If the grammar cannot express it, record a minimal
  failing example and follow data-platform Mode 6 for a reviewed custom step.
- **The publication:** `semantics` (full file or changes only),
  `completeness` and `effective_time`.

**Ask** the real decisions, one at a time, each with your recommendation:
- whether a record type, or a relationship type, is in scope;
- which of two fields is authoritative;
- a new MDM field or kind;
- each identifier;
- the source code's name, when the repo does not fix it.

Do not ask:
- what the repo's names already fix;
- whether a defect blocks (it does);
- which value fills a shared field, when the kind file already says.

**Write** `rules/sources/<source>/source.yaml`, following REFERENCE.md and
starting from its "Defaults".
- Write the values with `files.dumps`, or both files at once with
  `files.write_source(body, folder)`. In that body, each contract's quality
  block sits inside it as `mdm.<code>.contract.quality`, with its own
  `version`. `write_source` moves it into `quality.yaml`; without it, no
  `quality.yaml` is written. Then add short YAML comments by hand,
  between keys, wherever a choice needs a reason: an operator's answer, a
  field left out, a surprising path.
- Check it: `edgar-warehouse rules check --source <source>` loads it as
  `rules save` would, offline. Each file says `ok`, or `refused` with the
  error's kind; it checks that the file loads (the loader refuses a value
  YAML would guess), that each Bookkeeping target and the acquisition hold,
  and that the merge rules pass.
  Run it with no `--source` after a change to the merge rules.
- Write `source`, `bronze`, `execution`, `read` and `dataset_contracts` for a configured
  captured-file path. The source worker requires
  `execution: {profile: source.read, workers: 1, max_artifacts: 1}`; workers
  may be 1 or 2 and max_artifacts 1 to 512 (one reading reads many documents:
  a unit per document wastes a worker start on each). Declare `read.limits.max_bytes` at
  most 33554432 and `read.limits.max_records` from 1 to 100000. Choose bounds
  from measured inputs and split oversized captures into explicit units;
  see [READING.md](../data-platform/READING.md) for output and preparation limits. The `acquisition` section (how
  the platform captures the files) belongs to the Bookkeeping skill: leave it
  out for a feed onboarded from files already captured. The `bookkeeping`
  section is required: its `mastering` target (version 2, each step with its
  `units` and `input`) is what runs the feed into MDM, and without it nothing
  is mastered and **test** cannot run it. Write it with the
  [bookkeeping skill](../bookkeeping/SKILL.md) and its
  [SPEC](../bookkeeping/SPEC.md), shaped like an existing source's target
  (Examples); keep both sections as they are in an existing file.

**A new domain** also needs `rules/merge/kinds/<kind>.yaml`. Copy the shape
of an existing kind's file, and declare:
- `defaults.sources`: your source code;
- **a classification rule**, if the files hold more than one kind under one
  source type. The contract names it under `adapter.classification` (`kind`,
  `rule_id`, `version`). A rule written for another source cannot be
  reused as it is: the engine refuses a rule whose `source` differs, so
  port it under a new id, and its proof must be measured again on this
  source. A step whose verdict is another kind becomes `verdict: deferred`
  with `probable_kind: <that kind>`; otherwise it blocks the batch;
- **a matching rule on an issued identifier**, shaped like an existing
  kind's, with its Identifier Contract. Leave out
  `verification`: it is filled in when the operator approves the contract
  on its proving corpus;
- `bars`, from the kind's written requirements;
- `defaults.allow_unknown_effective: true` if records carry no effective
  date. If they carry one, map it as `effective_at` in the contract
  ([REFERENCE.md](REFERENCE.md)); a contract that names its effective time
  in plain words but maps no `effective_at` gives its records only the
  publication's time, often none.

Never add the new rules to `automatic_rules` in `rules/merge/policy.yaml`;
that happens only at **approve**. A matching rule on names is never written
here: it needs a measured proof, which is **refining-rules** work. When a
source's records can join another source's master only by name (they share
no issued identifier), list that name matching as its own part in
**plan-parts**, after the identifier rules, and take it through
refining-rules' **change-matching** ("Name matching across two sources"):
the kind is not mastered end to end until it is done. Say so in the log
rather than stopping silently.

**Execution target:** use the data-platform Parse and Master flow to declare
`source.read` → `mdm.prepare` → `mastering.merge`. Hand Bookkeeping the feed, target and verified worker profiles.

**Output:** `source.yaml` (and a new kind file, for a new domain) that loads
cleanly.
