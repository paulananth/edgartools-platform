Type: grilling
Status: open
Blocked by: 02
Labels: `wayfinder:grilling`

# Decide MDM Quality Evidence and Bookkeeping Admission

## Question

What immutable per-run evidence should the MDM pipeline produce, and how should
Bookkeeping verify and admit it?

Decide how evidence identifies the rule/check version, run, step, and work
unit; records rows evaluated and rows failed for each check; distinguishes
`flag`, `withhold`, and `exception`; avoids copying source values or provider
identifiers; and behaves on retries, concurrent attempts, incomplete runs, and
recovery. Reuse the completed Silver evidence contract where it fits, while
proving the MDM merge boundary can reproduce or retain the evidence after a
retry. Keep quality outcomes separate from overall pipeline status.

The answer must leave absent or incomplete evidence unknown and state the
recovery/enablement gate before a new receipt version can be used.
