-- The identifier index keeps no pending list (rebuild-priorities ticket 96).
-- Binding (ticket 77) finds the records holding a record's identifier through
-- this index, one value at a time. With fastupdate on (the default), new
-- entries wait in an unsorted list that every probe reads in full until a
-- vacuum merges it: on the N-PORT Proving Run's store (about 330,000 records)
-- 10,000 entries waited and one probe took 2.5 ms. Migration 012 turned the
-- list off for the two other indexes probed this way. The entries already
-- waiting are merged now.
ALTER INDEX mdm.stage_record_identifiers SET (fastupdate = off);
SELECT gin_clean_pending_list('mdm.stage_record_identifiers'::regclass);

COMMENT ON INDEX mdm.stage_record_identifiers IS
    'Finds the source records that carry one identifier of any namespace: binding probes it one value at a time, and edgar-warehouse context <kind> <namespace>:<value> reads it. No pending list (fastupdate off), so a probe costs the same however many saves came before.';
