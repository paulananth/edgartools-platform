"""The SEC Company source's governance inputs, read from `rules/`.

The Dataset Contract is `rules/sources/sec.submissions.company/source.yaml`
and the Mastering Policy is `rules/merge/`, edited and reviewed as files
(rules skill ticket 01). Preparation neither activates source coverage nor
binds identities.
"""

from edgar_warehouse.rules import files as rules_files

SOURCE_CODE = "sec.submissions.company.v1"
CONTRACT = rules_files.mdm_contract("sec.submissions.company", SOURCE_CODE)
FIELDS = CONTRACT["adapter"]["fields"]
POLICY = rules_files.policy()
APPROVED_ACTIVATION = next(rule for rule in POLICY["automatic_rules"] if rule["rule_id"] == "sec-company-candidate")
PROOF = APPROVED_ACTIVATION["proof"]
NAME_PROOFS = rules_files.pending_proofs()
