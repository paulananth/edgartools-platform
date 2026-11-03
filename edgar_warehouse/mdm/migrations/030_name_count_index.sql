-- Ticket 178: a Company record's matching trail keeps its Name Count entry under
-- `name_count` (it was `name_census`). The index that finds a record by the first LEI
-- of that entry follows the key. No data is rewritten: records are staged again.
DROP INDEX IF EXISTS mdm.stage_record_census_lei;
CREATE INDEX stage_record_name_count_lei ON mdm.stage_record USING btree ((((((((reading -> 'provenance'::text) -> 'matching'::text) -> 'name_count'::text) -> 'leis'::text) -> 0) ->> 0)));
