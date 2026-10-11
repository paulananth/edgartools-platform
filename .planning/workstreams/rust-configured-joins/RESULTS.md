# Configured collection/join qualification

Status: implementation and focused parity pass; Company/installed qualification,
independent reviews and delivery are in progress (see TICKET).

The release binding runs configured grouping, sorting, distinctness and joins
through source_engine.combine_tables. Authentication, bounded decoding, receipt
and output encoding, publication and independent execute/verify remain Python.
Native sorts release the GIL; canonical callbacks and opaque Python-object access
hold it. Python input/output objects remain; no fixed RSS cap or streaming claim.

Initially verified 118 affected public combination/nested/Company/reduction tests, including
five literal native/payload/failure regressions. Deterministic parity compares
1,500 cases against the pre-port source_combine at main cd277677, including 1,137
identical exception class/messages, stable order/types and unchanged inputs.
See parity.py and parity.json. No runtime fallback is retained. Review found a lone-surrogate metadata conversion
regression, corrected with Python-compatible surrogatepass tokens; 60 focused tests
and the expanded parity pass on the corrected release binding. Public escaped JSON
checks, filtering, grouping, ordering, distinctness and metadata-drop output pass.

Bounded cached Company measurement will be recorded separately; no performance,
activation, full-census construction or production mastering claim yet.
