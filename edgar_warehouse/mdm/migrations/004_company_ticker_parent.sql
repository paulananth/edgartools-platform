-- Add explicit ticker and parent company attributes to existing MDM stores.

ALTER TABLE mdm_company
    ADD COLUMN IF NOT EXISTS ticker TEXT;

ALTER TABLE mdm_company
    ADD COLUMN IF NOT EXISTS parent_company_entity_id UUID REFERENCES mdm_entity(entity_id);

UPDATE mdm_company
SET ticker = primary_ticker
WHERE ticker IS NULL
  AND primary_ticker IS NOT NULL;
