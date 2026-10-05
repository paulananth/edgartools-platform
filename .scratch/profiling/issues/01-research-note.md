# 01 Research note: classify, profile, RDM, agent context

Type: research. Phase: A. Blocked by: 00. Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [ ] Class definitions and tests (DAMA-DMBOK, ISO 8000)
- [ ] Profiling metrics; generic identifier detectors (pattern, check-digit families)
- [ ] Unique column combinations and inclusion dependencies (SPIDER, BINDER, Metanome); FK scoring; link tables
- [ ] Key design when no identifier exists
- [ ] Time models (as of / as at, snapshot vs changes, time series)
- [ ] Sensitive-data detection and masking
- [ ] Drift detection
- [ ] Hierarchy inference and storage for agents (parent+path, closure, ltree, nested sets, SKOS)
- [ ] RDM practice (ISO/IEC 11179, SKOS, code-set versions)
- [ ] Agent context design (bounded, self-describing, trust signals, text search)
- [ ] Unstructured extraction methods judged by the certainty rule
- [ ] Store-suggestion heuristics
- [ ] Snowflake-hosted Postgres features: ltree, pg_trgm, full-text search
- [ ] 2–3 open-licence candidates for trial B
- [ ] Reuse .scratch/data-quality/research/01-datakitchen-testgen-observability.md
- [ ] Operator approves the note
