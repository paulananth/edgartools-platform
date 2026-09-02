-- single-path-per-layer map, Ticket 03: skip-if-unchanged fast path for
-- full `mdm mastering`. Stores a content hash of the source row(s) a resolver
-- consumed at the time it last matched, so a later run can compare a fresh
-- hash and skip re-resolving an unchanged row entirely.

ALTER TABLE mdm_source_ref
    ADD COLUMN IF NOT EXISTS source_content_hash TEXT;
