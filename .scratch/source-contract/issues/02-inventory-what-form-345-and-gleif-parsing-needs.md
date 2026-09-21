# Inventory what Form 3/4/5 and GLEIF parsing needs

Type: research
Status: resolved (2026-09-21)
Blocked by: none

## Question

The `read` section must turn a Bronze Artifact into silver rows using named,
versioned primitives, with a per-source custom step allowed (Q4, Q6). Before
the vocabulary is decided, measure what the two proof sources actually need.

For **Form 3/4/5** (`edgar_warehouse/parsers/ownership.py`, `PARSER_VERSION
= "3"`) and **GLEIF** (find how GLEIF Level 1 is captured and parsed today;
see `.scratch/gleif-company-augmentation/` and Clean MDM's GLEIF inputs):

1. Every silver column each produces, and for each: source path (XPath /
   JSONPath / CSV column), the transform applied, and whether a generic
   primitive could express it.
2. Repeating groups and the row grain (Form 4: owners × transactions,
   `owner_index`, `txn_index`, `reporting_owner_count`).
3. Cross-source lookups (rule C-J's `submissions_lookup` from bronze
   `submissions.json`): can a generic `lookup(source, key)` primitive express
   it, or is it a custom step?
4. Logic that cannot be a primitive and would have to be a custom step, with
   the smallest honest boundary for it.
5. A draft primitive list with counts: how many columns each primitive
   covers, and what fraction of each source would be custom (check 11).

Local bronze only; zero SEC requests.

## Answer

[research/02](../research/02-parse-needs-inventory.md). Form 3/4/5: 58 silver
columns over 3 tables, 57 expressible by generic primitives; the one custom
step is `owner_display_name(owner_name_raw, owner_cik, payload) -> str`
(edgartools' classifier + name reversal), so 1.7% custom given a generic
`lookup(source, key, key_format, select, missing)` that returns found, sha256
and payload for rule C-J's nine evidence columns. Owners and transactions are
never crossed: transaction rows carry `owner_index = 1` plus
`reporting_owner_count`. GLEIF has no production parser or silver table (only
research scripts); a proposed 39-column Level 1 table is 0% custom, with the
difficulty in the reader (zipped streamed JSON array, fields that are an
object or a list, and a JSON-vs-XML format conflict with Clean MDM's specs).
Draft vocabulary: 16 primitives plus one custom step. Found on the way:
the C-J lookup takes the newest snapshot, not the one as of the filing date
(replay risk); `issuer_cik` is emitted but not a silver column; `owner_index`
/ `txn_index` are SMALLINT in `11_silver_landing_schema.sql:556-605`, against
the BIGINT rule.
