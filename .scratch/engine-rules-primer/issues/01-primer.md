# Engine rules primer grouped by function

Status: resolved

- [x] Inventory supported functions from native source parsing/evaluation, iteration, text, combination/reduction, adapter and MDM quality/matching/field owners. 2026-11-21 20:29 ET
- [x] Write the primer in 12 functional groups with invented examples and a README link. 2026-11-21 20:29 ET
- [x] Execute all 28 source-expression snippets, 10 iteration examples, 14 text operations, the four complete reading/normalization/combination/adapter-reading examples and exact-decimal preservation; documented outputs confirmed. All 11 fenced YAML blocks parsed. 2026-11-21 20:29 ET
- [x] Check vocabulary and local links: 158 documentation links resolve; 147 documentation checks passed; whitespace check clean. 2026-11-21 20:29 ET
- [x] Review Standards, Spec and GoF: clarify Parquet's worker path and count semantics; fix the nested-parent example found during execution. No remaining findings. 2026-11-21 20:29 ET
- [x] Learning → skill: none; primer links existing language owners without changing their procedures. 2026-11-21 20:29 ET

## Answer

`docs/engine-rules-primer.md` groups rules by file reading, value construction,
text normalization, conditions/source checks, lookups, combination/reduction,
MDM mapping, MDM quality, classification/matching, survivorship, relationships
and workflow/Silver/metadata. README links it from the rules guide.

Inventory covers the 28 source expressions, seven source checks, 14 text
operations, iteration forms, combination/reduction modes, nine quality checks,
three quality fixes, four matching/classification rule families and 13 policy
primitives. Exact parameter/limit contracts remain with the linked owners.
Partial examples name their prerequisites. Supported syntax is distinguished
from source-specific qualification, activation and deployment.

Examples ran against the existing native runtime through the source-engine
facade, using only invented local bytes and transient scripts outside Git.
No provider calls, database loads, new tests or production-code changes.

## Standards

Invented examples only. Worker-framed Parquet is explicitly distinguished from
direct eager parsing; ambiguous YAML, exact numeric handling and authority
boundaries are explained. Documentation checks and local links passed.

## Spec

Primer covers supported rule families with examples grouped by function.
The count check explicitly documents missing/list/scalar behavior.

## GoF

Documentation only; preserve current interpreter boundaries and link their
authoritative references. No pattern or code refactor is warranted.
