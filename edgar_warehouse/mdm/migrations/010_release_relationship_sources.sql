-- Canonical regulator identity required by the Form ADV private-fund contract.
ALTER TABLE mdm_fund
    ADD COLUMN IF NOT EXISTS private_fund_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mdm_fund_private_fund_id
    ON mdm_fund(private_fund_id)
    WHERE private_fund_id IS NOT NULL;

ALTER TABLE mdm_company ALTER COLUMN cik DROP NOT NULL;
