"""The SEC Company source's governance inputs, read from `rules/`.

The Dataset Contract is `rules/sources/sec.company/source.yaml`
and the Mastering Policy is `rules/merge/`, edited and reviewed as files
(rules skill ticket 01). Preparation neither activates source coverage nor
binds identities.
"""

from edgar_warehouse.rules import files as rules_files

SOURCE_CODE = "sec.company.v1"
CONTRACT = rules_files.mdm_contract("sec.company", SOURCE_CODE)
POLICY = rules_files.policy()
