# Write the Mapping Language reference

Type: research
Status: resolved (2026-09-21)
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

## Answer

[research/01](../research/01-mapping-language-reference.md). The `adapter`
block has 15 top-level, 7 per-profile and 7 per-relationship keys, each now
specified with type, meaning, rejection and `path:line`. **Nothing validates
a contract**: `register_dataset` stores any body (`store.py:180-233`) and the
table checks only that 8 keys exist (`023_clean_mdm.sql:18`); a contract
mistake raises `ValueError`/`KeyError` and stops the batch rather than
deferring a record. 13 unstated rules written down, including: a path
through a list returns `None` silently; relationships with a missing target
are dropped by a catch-all `ValueError`; `target_key` is never formatted
(an unpadded CIK names a different subject); a misspelled `field_shape` is a
no-op; `sec_cik` is the only format. **A dataset body can never change for a
`source_code`** (primary key) and `adapter_version` enters `assertion_id`, so
any mapping change today means a new `source_code` and re-binding every
record. Of the other Dataset Contract parts only `family`,
`schema_version`, `publication_families`, `publication_contract` and
`registry_evidence` change behaviour; `semantics` is never read and
`completeness` is optional free text. Proposed closed value sets are marked
PROPOSED. Gaps for GLEIF and Form 3/4/5 are written as Codex proposals;
the reporting-owner silver row lacks an issuer CIK, so `INSIDER_OF` needs a
join or a new column (connects to research 02's dropped `issuer_cik`).
