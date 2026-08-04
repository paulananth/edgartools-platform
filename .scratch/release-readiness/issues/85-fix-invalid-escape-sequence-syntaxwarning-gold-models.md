Type: task
Status: resolved

## Question

`edgar_warehouse/serving/gold_models.py` lines 583 and 659 embed the DuckDB
regex pattern `'\s+'` inside plain (non-raw) Python string literals, as part
of the `party_nk` owner-name-normalization SQL (`regexp_replace(...,'\s+',
' ','g')`, used twice in what looks like near-duplicate CASE blocks). `\s`
is not a recognized Python escape sequence, so Python 3.12+ emits:

```
edgar_warehouse/serving/gold_models.py:583: SyntaxWarning: invalid escape sequence '\s'
edgar_warehouse/serving/gold_models.py:659: SyntaxWarning: invalid escape sequence '\s'
```

Found incidentally 2026-08-04 while verifying the freshly-built prod MDM
image for release-readiness ticket 84's deploy (`docker run --entrypoint
python <mdm-ref> -c "from edgar_warehouse.serving.gold_models import
iter_gold_tables"` surfaced both warnings on import). Not related to ticket
84's lease work -- pre-existing in this SQL template, unrelated code path.

**Not yet a functional bug**: Python currently still passes the literal
`\s` characters through unchanged when the escape isn't recognized, so the
SQL text DuckDB receives today is correct. This is a forward-compatibility
warning only -- a future Python version turns unrecognized escapes into a
hard `SyntaxError`, at which point this becomes a real breakage, not just
warning noise.

**Fix**: change both occurrences to a raw string (`r'\s+'`) or an escaped
literal (`'\\s+'`) so the pattern is unambiguous today and doesn't
regress when Python tightens this. Trivial, single-session, no design
decision involved -- add a regression assertion (e.g. a test importing the
module under `-W error::SyntaxWarning` or `python -W error -c "import
edgar_warehouse.serving.gold_models"`) so a future reintroduction fails
loudly instead of silently reappearing as warning noise.
