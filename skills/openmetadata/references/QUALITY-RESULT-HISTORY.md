# Quality result history

Keep a distinct native result for each case and load, using its timestamp as
the history key. Read back the exact timestamp with `startTs` and `endTs` set to
it, then compare status, checked and failed counts, and result detail. A
successful HTTP response alone does not confirm publication.

Treat an identical result at the same timestamp as an idempotent replay.
Duplicate or mismatching history is an error to resolve, not a reason to POST
again blindly. On OpenMetadata 2.0.2, a timestamp-specific `PATCH` can correct
one mismatching result; make at most one correction attempt, then require exact
readback.

This API behavior does not establish that the platform supplied complete,
verified evidence for the load. Preserve an incomplete run as unknown, and
publish only results backed by admitted load evidence.
