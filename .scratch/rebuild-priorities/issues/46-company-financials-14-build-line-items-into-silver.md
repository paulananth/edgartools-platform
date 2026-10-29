# 14 Build: standard line items into silver

Priority: 46, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/14-build-line-items-into-silver.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: in progress (Claude, branch `claude/t46-line-item-codes`). Blocked by: 38, 42, 43, 45. Map: [map](../../company-financials/map.md).

## Question

Implement the line-item selection (ticket 38's rules; ticket 42's reporting currency, `ifrs-full` lists, kind flags and statement format from the SIC code) and land the silver table of ticket 11 through the silver writer (profiling ticket 06), with each value's chosen concept and accession. Acceptance: none of the research note's nine hazards (section 5) is possible; the answer key's line items match.

## RDM: the line items as a code set (operator, 2026-10-22)

"Yes, code set + crosswalk (Recommended)", asked "Do you need ifrc or gaap labels in
rdm": the 19 standard line items are an RDM code set (`financial-line-items`: code,
label, definition, kind), crosswalked to the `us-gaap` and `ifrs-full` concepts each
uses (outside standards, `to_version: outside`). The rules YAML names those RDM codes
and holds only the try-order and the computed fallbacks, which a crosswalk cannot
express. The taxonomies themselves are not loaded into RDM. (Corrected 2026-10-28
20:20 ET, below: a concept's label and description are not kept in silver.)

- [x] The RDM code set `financial-line-items` drafted, its crosswalk to research 01
  and 04's concepts, approved in the operator's words and published: see Parts
- [x] The rules YAML names the RDM codes; a test holds every concept in its lists
  equal to the code set's crosswalk: see Parts

## Parts (listed 2026-10-28 16:13 ET)

Found (2026-10-28 16:13 ET): nothing of the build exists yet. `rules/sources/sec.company-facts/facts.yaml`
reads the facts (ticket 45), but no target lands `company_fact` in silver, and no
rule names a line item. Two rulings differ on how the line items are built:
ticket 38 (answer 6) "a configured step applies it", with a generic engine primitive
for an operation the engine lacks; ticket 43's spec "built by dbt from company_fact".
dbt in this repository runs on Snowflake only, and the cohort proof (48) runs on local
stores (operator, 2026-10-21: "Two proofs, local").

- [x] Ruling: where the line items (and the facts' flattening) are built for the local proof (2026-10-28 16:44 ET): operator: "Engine step, local (Recommended)": the engine lands `company_fact`, flattened, through the silver writer into local PostgreSQL; a configured combine step applies the line-item map, with a generic "first present in order" operation added to the engine; ticket 43's "built by dbt" corrected to this; Snowflake receives the same silver later
- [x] Found (2026-10-28 16:49 ET): the line items are 23 codes, not 19: research 01's 19 groups with group 15
  split into current assets and liabilities, 16 into pretax income and income tax, 19 into
  dividends paid, buybacks and dividends per share; the answer key (ticket 44) names the same 23
- [x] The RDM code set `financial-line-items` version 1, as reviewed (see the review line) (2026-10-28 16:49 ET): 23 codes (label, definition, property
  `period`: 15 duration, 8 instant), 121 crosswalk rows to `us-gaap`, `ifrs-full` and `dei` (outside):
  76 close (a concept tried as the line item), 7 broad (flagged "includes ..."), 38 narrow (another
  flag, or a computed value's term); drafted, approved and published on a disposable PostgreSQL 16
  (`.scratch/company-financials/line-items/draft_codes.py`), sha256 `035e1f56…`, pinned in
  `rules/reference/published/financial-line-items/1/`. Approved under the standing approval:
  operator, 2026-10-22: "Yes, code set + crosswalk (Recommended)"; 2026-10-15: "Approved the rules always"
- [x] GoF consult before the engine change (2026-10-28 17:35 ET): leave `iteration.rs`'s dispatch (six commits each
  added one small arm); `nest` in its own module like `matrix` and `parallel`, its arm before the
  `objects` fall-through; one `branches` helper so `expressions` and `needs_order` recurse into both
  `choose` and `nest`
- [x] Engine: `each.nest` (2026-10-28 17:35 ET): an iteration inside each row of another, `keep` carrying named outer
  fields onto each inner row; every inner row counts against `max_records`; an inner row must be an
  object, a kept field never replaces one. `crates/source-contract/tests/nest.rs` 4 passed; the crate's
  tests 221 passed; READING.md documents it
- [x] `company_fact` lands in silver (2026-10-28 17:35 ET): facts.yaml's `company_fact` table (taxonomy, concept and unit
  nested onto each fact; the exact figure; currency from the unit; a 10-digit company key) and
  `silver-company-fact.yaml`. Found: the silver writer refuses an empty key column, and ticket 43's key
  held `period_start`, empty for an instant; the key now reads `period` (start/end, or the instant's
  date). Every captured file read (`.scratch/company-financials/reader/fact_rows.py`, 318 s): 368 files,
  5,134,979 facts, as many distinct keys, every file equal fact by fact to the file read directly in
  exact decimals; 4,686,212 facts in one of 23 currencies. Tests: `tests/integration/test_company_fact_silver.py`
  3 passed (the rows, the spec, landed exact once with the Company's MDM id); the engine, mapdoc, catalog
  and configured-master tests 1,166 passed (8 min, over the 5-minute local bound: the engine change reaches
  every engine test). Landing runs by `edgar-warehouse silver land`, as N-PORT's holdings do; Bookkeeping
  has no silver step yet
- [x] Found (2026-10-28 17:35 ET), for the operator: the ruling "each fact keeps its concept's label and description in
  silver" (ticket 46, RDM section) has no column in ticket 43's approved `company_fact`; carrying them on
  each of 5.1 million facts repeats each concept's text thousands of times
- [x] Ruling: a concept's label and description stay out of silver (2026-10-28 20:20 ET): operator, 2026-10-28:
  "consult data-modeling skill and how to keep financial so that is it easy to calculate cgar and other analytics
  do not complecate too much". By the data-modeling skill, a concept's label is reference data of an outside
  standard (the taxonomy), the same on every fact of that concept, so it never goes on a transaction row (sections
  1 and 6: one system of record, no repeated master or reference field). Measured: 8,495 concepts over 139,643
  filer-concept pairs; 57 concepts worded differently between filers; 1.9 MB of text if held once. No analysis
  needs it: CAGR and the measures read `company_line_item` (one row per company, line item and annual period;
  the default copy `is_latest`) and `company_measure`, and a line item's label and definition are RDM's
  `financial-line-items`. So no label column and no concept table; a concept table is added only when a use
  needs it
- [x] Three-axis review of PR 2 (2026-10-28 17:37 ET). GoF: leave it (each kind is one small arm; `nest` in its own
  module). Standards, acted on: the filer once (`company_key`, the link's 10-digit CIK; `cik` dropped, one
  system of record); one shared field-name check; a kept field the outer row lacks refuses
  (`nest_field_missing`); clearer limits. Spec, acted on: the figure check is the writer's own (a figure a
  DECIMAL column cannot hold exactly is refused; PostgreSQL would round extra places silently): of the
  5,134,979 captured figures the longest has 20 whole digits and 6 after the point; the link's
  `inclusion: 1.0`; a test that an unknown taxonomy still refuses the file; the skill's "no new iteration
  primitive" and ticket 43's key corrected. Noted: `currency` is three capital letters before any `/`, not
  checked against the ISO list (23 distinct in the capture)
- [x] PR 2 (engine `nest`, `company_fact`): PR, CI, merge (2026-10-28 17:52 ET): #1209 merged, 20 of 20 checks
- [x] The line-item map `rules/sources/sec.company-facts/line-items.yaml` (2026-10-28 16:49 ET), version
  `line-items-2026-10-28.first-build`, naming the code set: the `us-gaap` and `ifrs-full` try-orders,
  the flags, the industry kinds and the computed fallbacks (sum or difference of terms; a term a
  concept, the first of several, another line item, or optional). Checked locally against the
  answer key's lists: 23 items, 0 differences
- [x] A test holds every concept in the map's lists equal to the code set's crosswalk (2026-10-28 16:49 ET):
  `tests/unit/test_financial_line_items.py` (the codes, both taxonomies, each computed entry's line
  items, the crosswalk equal), 2 passed; RDM, sequence, rules-digest and company facts tests 288 passed;
  `rules check --source sec.company-facts` ok
- [x] Three-axis review of PR 1 (2026-10-28 16:55 ET). GoF: leave the grammar; the engine PR parses the map once (one
  module, the test and the draft script importing it), refuses a leading optional term and a line-item
  cycle. Standards, acted on: a computed value's terms left the crosswalk (inputs, not SKOS mappings);
  each flag's match type stated (`FLAG_MATCH`, "cover-page date" close), not read from its words; a
  test of expected match types; published to a scratch folder and copied; the approval's one ruling in
  its words. The code set is now 90 crosswalk rows (77 close, 7 broad, 6 narrow), sha256 `2b0026bf…`.
  Spec, acted on: total debt's forms toward research (us-gaap form 2 adds short-term borrowings; IFRS
  long-term plus short-term, else current, borrowings; the third IFRS form could never fire), the
  answer key the same (no value moved, ticket 44); a computed value names its first fact term's
  accession; the skill's stale lines and ticket 43's "built by dbt". Noted: no REIT concept (research
  01 lists none); a lone reported total (`Borrowings`, `LongTermDebt`) carries "computed" as the key
  does. Tests 3 passed
- [x] PR 1 (configuration): PR, CI, merge (2026-10-28 17:08 ET): #1208 merged, 20 of 20 checks
- [ ] `company_line_item` built: first present wins per company and annual period, latest
  copy `is_latest`, fiscal year (Compustat FYEAR), period kind, null with its reason,
  statement format ("unknown" until Company is mastered), the revenue quality check
- [ ] Tests: none of research 01 section 5's nine hazards possible; the answer key's
  line items match (ticket 44)
- [ ] GoF consult before code; three-axis review; PR, CI, merge
- [ ] Learning → skill
