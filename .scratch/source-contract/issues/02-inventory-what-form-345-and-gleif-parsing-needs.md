# Inventory what Form 3/4/5 and GLEIF parsing needs

Type: research
Status: claimed
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
