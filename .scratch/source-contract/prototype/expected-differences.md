# Expected differences: Form 3/4/5 contract vs `ownership.py` (written BEFORE the comparison)

The prototype's Form 3/4/5 Source Contract is compared with today's parser
(`edgar_warehouse/parsers/ownership.py`, `PARSER_VERSION = "3"`) over the local
bronze corpus (5,356 artifacts). Every difference below is decided in advance.
**Any difference not listed here is a failure of the language, not a finding.**

| # | Column(s) | Expected difference | Why (decision) |
|---|---|---|---|
| 1 | `parser_version` (all tables) | `"3"` → the contract's constant | Versioning moves to the contract digest (ticket 06). Excluded from comparison. |
| 2 | `transaction_shares`, `transaction_price`, `shares_owned_after`, `acquired_disposed_code`, `ownership_direct_indirect`, `ownership_nature` | May differ **only** where the element has descendant text outside `<value>` (e.g. a `<footnoteId>` with text) | Research 10 (b): paths read `<value>` (`.value.$`); today reads all descendant text. Expected count: 0 or near 0. |
| 3 | `owner_submissions_*`, `owner_name` | None on this corpus | The local submissions copy is flat (one undated file per CIK), so `as_of` + `earliest_after` selects the same file as `newest`. **Ticket 04 Q3 is therefore unproven by this comparison**; it is proven separately on a synthetic dated layout (engine self-test), and the capture-date assumption is checked against S3 separately. |
| 4 | Contract adds `owner_kind` (owner table) | New column, absent from the oracle | The Dataset Contract's adapter needs a kind per row (`adapters.py:61-68`); the contract derives it with a declared custom step. Compared on oracle columns only. |
| 5 | Artifacts where a child that should occur once occurs twice | The contract fails that artifact with "path crosses a repeating group"; today takes the first | Research 10 (a): crossing a list is a located error, not a silent first match. Counted and listed; each one is a finding about the data, not an allowed silent difference. |

Anything else — a row count per table, any other column, any row order — must be identical.
