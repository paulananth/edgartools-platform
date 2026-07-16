# Domain Docs

How engineering skills consume this repository's domain documentation.

## Before exploring

- Read `CONTEXT.md` at the repository root.
- If a root `CONTEXT-MAP.md` is introduced later, use it to locate each relevant context glossary.
- Read ADRs under `docs/adr/` that touch the area being explored.
- If a referenced domain file does not exist, proceed silently; domain-modeling creates files lazily when terms or decisions are resolved.

## Layout

This is a single-context repository:

```text
/
├── CONTEXT.md
└── docs/
    └── adr/
```

## Vocabulary

Use the canonical terms defined in `CONTEXT.md` in ticket titles, plans, hypotheses, tests, and user-facing explanations. Avoid synonyms that the glossary explicitly rejects.

If a needed concept is absent, either reconsider whether it belongs to this domain or surface the gap for domain modeling.

## ADR conflicts

If proposed work contradicts an existing ADR, identify the conflict explicitly rather than silently overriding the decision.
