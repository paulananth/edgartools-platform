# Configured collections and joins review

Baseline: cd27767713ba651b6531b3ebb6ba61192d105905 (merged #920).
Initial implementation: cc13eef5, independently reviewed on three axes.
Spec: TICKET.md and agreed configured Rust core / Python callers and custom code.

## Standards

Zero documented breaches; one correctness finding: Rust String extraction rejected
lone-surrogate metadata accepted by the authenticated JSON codec. The prior worker
could join/filter/sort by it and drop it before publishing valid UTF-8 output.
Correction uses injective UTF-8 surrogatepass metadata tokens for keys, textual
ordering and canonical comparisons, with a fast path for valid UTF-8. Empty-string
checks use length. Opaque payloads and final output encoding remain unchanged.
Public red/green regression covers all affected paths; 60 corrected focused tests
and 1,500 expanded parity cases pass. Independent reviewer verified equality and
Python code-point ordering across 2,025 representative string pairs. Resolved;
no remaining findings or material heuristic smells.

## Spec

Zero missing, unasked or incorrect implementations found. Independently probed
multi-group and multi-column ordering, signed zero/stable ties, whole-row identity
and nested copying. Typed keys, raw flatten bounds, original-row keys, complete
validation before publication and unchanged receipt authority are preserved.
Qualification/delivery gates remain on the ticket until verified.

## GoF

Clear. Retain existing facade and functional adapter. History #819/#822/#827/#830/
#854/#878/#911 demonstrates grammar/authentication evolution at existing seams;
new Strategy/Interpreter/Visitor/Composite classes would add indirection without
reducing a demonstrated maintenance cost. Rust type dispatch validates boundary
semantics. No additional refactor recommended.
