# Connecting MDM To Neo4j

The MDM graph sync uses the official Neo4j Python driver over Bolt. Neo4j is an
external runtime dependency; Terraform and application deploy scripts should
create or reference secret containers, but secret values are populated by an
operator outside Terraform state.

## Runtime Variables

The current MDM CLI and API read these variables:

```bash
export NEO4J_URI="neo4j+s://<instance-id>.databases.neo4j.io"
export NEO4J_USER="<neo4j-user>"
export NEO4J_PASSWORD="<neo4j-password>"
```

Neo4j Aura often displays `NEO4J_USERNAME` and `NEO4J_DATABASE`. Map
`NEO4J_USERNAME` to `NEO4J_USER` before running this repo. `NEO4J_DATABASE` is
useful for manual Cypher sessions, but the MDM graph client currently uses the
driver's default database.

The runtime can also read one JSON secret through `NEO4J_SECRET_JSON`:

```json
{"uri":"neo4j+s://<instance-id>.databases.neo4j.io","user":"<neo4j-user>","password":"<neo4j-password>"}
```

## AWS Secrets Manager

For AWS ECS MDM tasks, populate the Terraform-created secret named
`edgartools-<env>/mdm/neo4j` with the JSON payload above:

```bash
aws --profile <admin-profile> --region us-east-1 secretsmanager put-secret-value \
  --secret-id edgartools-dev/mdm/neo4j \
  --secret-string '{"uri":"neo4j+s://<instance-id>.databases.neo4j.io","user":"<neo4j-user>","password":"<neo4j-password>"}'
```

`infra/scripts/deploy-aws-application.sh` reads the Terraform output
`mdm_neo4j_secret_arn` and injects that secret into ECS as
`NEO4J_SECRET_JSON`. The runner execution role must be applied from
`infra/terraform/access/aws/accounts/<env>` so ECS can read the secret.

## Azure Key Vault

For Azure Container Apps, use `infra/scripts/bootstrap-azure-secrets.sh`:

```bash
bash infra/scripts/bootstrap-azure-secrets.sh \
  --key-vault-name <key-vault-name> \
  --mdm-neo4j-uri "neo4j+s://<instance-id>.databases.neo4j.io" \
  --mdm-neo4j-user "<neo4j-user>" \
  --mdm-neo4j-password "<neo4j-password>"
```

The script stores split secrets (`mdm-neo4j-uri`, `mdm-neo4j-user`,
`mdm-neo4j-password`) and a JSON `mdm-neo4j` secret.

## Local Verification

Install the MDM extra and run a graph-only connectivity check without printing
the password:

```bash
python -m pip install -e ".[mdm]"

python - <<'PY'
import os
from neo4j import GraphDatabase

uri = os.environ["NEO4J_URI"]
user = os.environ["NEO4J_USER"]
password = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(uri, auth=(user, password))
try:
    with driver.session() as session:
        print(session.run("RETURN 1 AS ok").single()["ok"])
finally:
    driver.close()
PY
```

After `MDM_DATABASE_URL` is also configured, run the full MDM runtime check:

```bash
edgar-warehouse mdm check-connectivity --neo4j
```

## Fleet Tokens

Some Neo4j management workflows provide a Fleet token and instruct operators to
run a `system` database procedure such as `fleetManagement.registerToken`.
Treat those tokens as secrets; they may contain private key material.

Before registering a token, verify that the procedure exists on the target
instance:

```cypher
USE system;
SHOW PROCEDURES
YIELD name
WHERE name = 'fleetManagement.registerToken'
RETURN name;
```

If the procedure is absent, Aura returns `ProcedureNotFound`; use the Neo4j
Console workflow for that instance or confirm that Fleet management is enabled
for the target deployment. Rotate any Fleet token or Neo4j password that was
exposed in terminal logs or chat.
