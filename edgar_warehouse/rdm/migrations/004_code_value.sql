-- A code may carry one typed value for its period (ticket 133): a statutory
-- rate, a threshold. The value is exact decimal text, as filed, never a float;
-- its unit says what it measures. Both or neither. Existing codes hold neither,
-- so every version already published keeps its canonical bytes and its pin.
ALTER TABLE rdm.code
  ADD COLUMN value text CHECK (value ~ '^-?[0-9]+(\.[0-9]+)?$'),
  ADD COLUMN unit text CHECK (btrim(unit) <> ''),
  ADD CONSTRAINT code_value_has_unit CHECK ((value IS NULL) = (unit IS NULL));
COMMENT ON COLUMN rdm.code.value IS 'The code''s value for its period (valid_from to valid_to), as exact decimal text; empty for a code that only names something.';
COMMENT ON COLUMN rdm.code.unit IS 'What the value measures, such as "percent of taxable income"; set exactly when value is.';
