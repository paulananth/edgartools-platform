# Fix the DEF 14A executive-record parser leaking role text into exec_name

Type: task
Status: open
Blocked by: none

## Question

Nothing to decide on this map. Research 01 found 47% of
`sec_executive_record.exec_name` values are role vocabulary ("Chairman of
the", "President and Chief", "Executive Officer") and the top "names" by
issuer count are job titles. `edgar_warehouse/parsers/proxy_fundamentals.py`
is splitting the compensation-table name/role columns wrong for roughly half
of issuers. Until fixed, the proxy source cannot participate in any Person
binding rule (ticket 02 treats it as review-only evidence).

This is production parser code: it needs its own branch, the mandatory
`/gof-refactor-reviewer` consult, the three-axis `/code-review`, and a
re-export before research 01's proxy figures can be re-measured. Whoever
owns `edgar_warehouse/parsers/` takes it; this map only needs the fixed
export to exist. Resolved when a re-run of research 01's quality check
shows plausible-name rate comparable to the 8-K source (~98%).
