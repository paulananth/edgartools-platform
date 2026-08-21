# Decide the bronze consumption ledger and source cursor contract

Type: grilling
Status: open
Blocked by: none

## Question

What exact identity, ordering, completeness, and disposition contract lets a
bronze replay select only never-consumed or content-modified source material
without changing Bronze Persist's optional role?

Decide the contract across submissions snapshots, pagination files, filing
artifacts/accessions, company facts, reference catalogs, and ADV bulk inputs:
object key/version/content hash, logical source key, parser/config version,
accession/document completeness, late arrival, explicit repair, retry, and the
rule for advancing a cursor only after silver publication succeeds. Resolve how
newer dated bronze objects supersede intact older checkpoints and how immutable
SEC conflicts fail closed without last-writer-wins behavior.
