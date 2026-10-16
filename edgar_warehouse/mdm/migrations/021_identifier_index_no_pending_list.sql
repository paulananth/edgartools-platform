-- The identifier indexes keep no pending list (rebuild-priorities ticket 96).
-- Binding (ticket 77) finds the records holding a record's identifier through
-- stage_record_identifiers one value at a time, and cross_reference_lookup
-- probes stage_record_cross_references the same way. With fastupdate on (the
-- default), new entries wait in an unsorted list that every probe reads in
-- full until a vacuum merges it. Over 40 N-PORT batches of 1,000 records
-- (store 20,311 to 60,311), a batch took 4.36 s on average with the list and
-- 2.51 s without; a profiled batch's identifier probes took 0.8 to 3.8 s with
-- it and 0.05 to 0.24 s without. Migration 012 turned the list off for the
-- two other indexes probed this way. The entries already waiting are merged
-- now.
ALTER INDEX mdm.stage_record_identifiers SET (fastupdate = off);
ALTER INDEX mdm.stage_record_cross_references SET (fastupdate = off);
SELECT gin_clean_pending_list('mdm.stage_record_identifiers'::regclass);
SELECT gin_clean_pending_list('mdm.stage_record_cross_references'::regclass);

COMMENT ON INDEX mdm.stage_record_identifiers IS
    'Finds the source records that carry one identifier of any namespace: binding probes it one value at a time, and edgar-warehouse context <kind> <namespace>:<value> reads it. No pending list (fastupdate off), so a probe costs the same however many saves came before.';
