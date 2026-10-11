# Review against e4be3019

Three independent axes required by code-review and CLAUDE.md:1327–1339.
Implementation checkpoint a215d3ba, correction bf2278e3.

## Standards

Initial: 0 documented breaches, 1 correctness finding, 0 actionable design smells.
The adapter marshalled unused future operands before the as-of filter. A future
merge carrying `depends_on=None` was ignored at baseline and rejected by serde.
Resolved by bf2278e3: filter before marshalling, preserve caller override objects,
and leave withdrawn merge survivor/dependency metadata uninterpreted. Independent
baseline comparisons passed. No remaining Standards findings.

## Spec

Initial: 1 wrong implementation, 0 missing requirements, 0 unasked scope changes.
The same eager interpretation violated the ticket's public API and correction
parity requirement; independently reproduced with future `survivor=17`.
Resolved by bf2278e3. Independent baseline comparisons and reference identity
checks passed for future and reversed commands. No remaining Spec findings.
Python-owned policy, custom code, history folding, canonical comparisons and
orchestration match the bounded spec; the native loops release the GIL and all
changed computation dependencies participate in worker runtime identity.

## GoF

Leave the design as implemented. No actionable findings. Existing facade and
adapter boundaries have evidence across reading/reduction changes; replay is a
fixed operation vocabulary rather than an interchangeable algorithm hierarchy.
History shows independent field/profile policy evolution, appropriately retained
in Python with shared selection. Additional State/Command/Strategy classes would
add review and debugging cost without reducing demonstrated current costs.

Summary: initial findings Standards 1, Spec 1, GoF 0; remaining 0 on each axis.
