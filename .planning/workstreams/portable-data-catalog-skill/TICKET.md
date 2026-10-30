# Portable data catalog skill

Scope: study official terminology, qualify an invented connected metadata model
through the existing local API, then write a portable skill with a pinned
OpenMetadata reference. Support a catalog and independent visualization together.
No computer use, source requests, real records or production pipeline execution.

- [x] Study business meaning, domains, technical hierarchy, layers, products, quality and lineage in official references. — 2026-10-30 15:44 ET: official documentation and pinned 2.0.2 schemas/implementation reviewed; references retained in the skill.
- [x] Test one connected invented model through the native API before writing the skill; retain counts/outcomes and remove only exact test-owned objects. — 2026-10-30 15:44 ET: final rerun passed all associations, wrong-mapping and repeat checks; 14 objects and 1 edge removed, zero remaining.
- [x] Create a vendor-neutral skill and separate OpenMetadata instructions; document Alation/Collibra terminology differences without claiming live support. — 2026-10-30 15:44 ET: data-catalog core plus MODEL/OPENMETADATA/PORTABILITY references; preserves both operator browsing/destination choices.
- [x] Validate realistic skill use, source-neutrality, references and packaging discovery. — 2026-10-30 15:44 ET: independent forward-test; skill validator; 94 genericity/path tests; 5 exact wheel files; actual installer into both temporary runtime folders.
- [ ] Publish a PR and report verified head; keep unfinished qualification explicit.
- [x] Learning → skill: data-catalog captures dimension separation, portable identity/mappings, honest native-versus-renderer capability and columns-plus-tags readback. — 2026-10-30 15:44 ET: native proof and independent behavioral test support these instructions.

Operator decisions: each configured entity kind is a business domain; metadata
and semantics remain configuration-driven. The catalog and visualization are
independent projections of that meaning. Bookkeeping records successful
artifacts for resuming; Change Journal avoids unnecessary repeat processing.
Operational diagnostics and execution enforcement stay in data-operations.
