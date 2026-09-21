# Write the Mapping Language reference

Type: research
Status: claimed
Blocked by: none

## Question

Clean MDM's `adapter` block is the Source Contract's mapping into MDM (Q8),
but it is specified only by code: `edgar_warehouse/mdm/clean/adapters.py:49-158`
and one instance, `edgar_warehouse/mdm/clean/company_source.py:32-61`. The
Dataset Contract around it has one line in
`docs/specs/clean-mdm/source-evidence.md:23`.

Produce the reference from primary sources (the code, its tests, the
clean-mdm specs), citing `path:line` for every claim:

1. Every `adapter` key: type, required or optional, meaning, the rejection
   (`UnsupportedRecord` reason) it can raise, and an example.
2. Rules the code applies that no document states — at least: dotted paths
   with no arrays (one row → one assertion); kind as exact value lookup;
   relationships dropped silently when the target key is missing; the single
   `field_shape`; the single identifier format; what `adapter_version` pins
   and when it must change.
3. Every other Dataset Contract part (`provider`, `family`, `schema_version`,
   `record_key`, `publication_key`, `effective_time`, `semantics`,
   `completeness`, …): what the code reads, what is prose only, and the
   closed set of values each should take for a validator to check it.
4. The gaps a GLEIF and a Form 3/4/5 contract would hit, written as
   proposals for Codex (not edits).
