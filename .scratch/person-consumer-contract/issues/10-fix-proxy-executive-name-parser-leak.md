# Fix the DEF 14A executive-record parser leaking role text into exec_name

Type: task
Status: open
Blocked by: none

## Question

Nothing to decide on this map. Research 01 found 47% of
`sec_executive_record.exec_name` values are role vocabulary ("Chairman of
the", "President and Chief", "Executive Officer") and the top "names" by
issuer count are job titles. **Corrected by research 12**: the platform's
`edgar_warehouse/parsers/proxy_fundamentals.py:108` copies `entry.name`
verbatim from the *edgartools* PyPI package (5.30.0,
`edgar/proxy/html_extractor.py:857-864`), whose row walk overwrites the
current name with wrapped title fragments on multi-year compensation
blocks. Two repair points: upstream in edgartools, or a platform-side
carry-forward in `proxy_fundamentals.py:100-118`. See
[research 12](../research/12-proxy-executive-person-pipeline.md) for the
mechanism and a proposed test. Note research 12 F8: the per-filing fetch
has no `--force`, so a parser fix alone will not re-parse already-marked
accessions. Until fixed, the proxy source cannot participate in any Person
binding rule (ticket 02 treats it as review-only evidence).

This is production parser code: it needs its own branch, the mandatory
`/gof-refactor-reviewer` consult, the three-axis `/code-review`, and a
re-export before research 01's proxy figures can be re-measured. Whoever
owns `edgar_warehouse/parsers/` takes it; this map only needs the fixed
export to exist. Resolved when a re-run of research 01's quality check
shows plausible-name rate comparable to the 8-K source (~98%).
