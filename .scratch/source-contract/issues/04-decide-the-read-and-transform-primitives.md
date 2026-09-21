# Decide the read and transform primitives and the custom-step signature

Type: grilling
Status: open
Blocked by: 02

## Question

From ticket 02's inventory, decide the `read` section's vocabulary:

- readers by format (`xml`, `json`, `csv`, `html_table` …) and how paths and
  repeating groups are written;
- the transform primitives, their parameters and `name@version` rules;
- the custom-step signature (input: Bronze Artifact or rows; output: rows;
  no fetch, write or MDM call) and how a contract declares one;
- how `person_name@v2` (ticket 25 of the Person map) and the C-J lookup fit.
