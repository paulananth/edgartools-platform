# OpenMetadata credentials and token lifetime

The local server is pinned to OpenMetadata 2.0.7. The repository initializer
bootstraps its local administrator and keeps the login and API token in the
ignored repository-root `.env` file (mode `0600`). It does not print either
secret. Read [LOCAL-SERVER.md](../LOCAL-SERVER.md#edgartools-instance-and-private-credentials)
before starting the service or accessing those values.

## Local bootstrap

`bash infra/openmetadata/init.sh` starts the isolated `edgartools-openmetadata`
Compose project, waits for health, and calls
`infra/openmetadata/credentials.py`. On first startup the helper:

1. Verifies that the endpoint is local HTTP and the server reports 2.0.7.
2. Generates a shell-safe administrator password and writes the credentials to
   `.env` with restrictive file permissions.
3. Changes the default administrator password through
   `PUT /api/v1/users/changePassword`.
4. Logs in through `POST /api/v1/users/login`, issues a 30-day personal access
   token through `PUT /api/v1/users/security/token`, and verifies it with
   `GET /api/v1/system/version`.
5. Saves the PAT as `OPENMETADATA_TOKEN` in `.env` for normal catalog CLI use.

If the saved PAT still reads the pinned server version, initialization retains
it. If it is expired, initialization uses the saved login to issue and verify a
replacement. Do not print `.env`, place values in command arguments, or commit
the file. When a client needs the values, load `.env` in a shell with tracing
disabled and pass the exported variables directly to that client. Normal rules
catalog commands should read `OPENMETADATA_TOKEN`; use login variables only for
an API login or token refresh.

## 2.0.7 API contract

The 2.0.7 release source defines `PUT /users/changePassword` and
`PUT /users/security/token`. Its personal-token request requires `tokenName`
and `JWTTokenExpiry`; `30` is a supported 30-day choice. The response exposes
the generated `jwtToken` at issuance, so the helper persists that value
immediately and never writes it to tracked files. See the version-pinned
[user API implementation](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/openmetadata-service/src/main/java/org/openmetadata/service/resources/teams/UserResource.java),
[personal-token request schema](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/openmetadata-spec/src/main/resources/json/schema/auth/createPersonalToken.json),
and [password-change request schema](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/openmetadata-spec/src/main/resources/json/schema/auth/changePasswordRequest.json).

OpenMetadata login returns a short-lived access token; the initializer uses it
only to issue the PAT. Do not store that login response as the operational
token. If the endpoint, server release, request schema, or token response
changes, qualify that release's API before changing the helper. Never assume
rolling documentation matches the pinned server.

The 30-day PAT carries the administrator's permissions. Keep it local to this
developer environment; do not repurpose it as a shared service identity or
publish it to other systems. A separate bot identity requires an explicit
permission design and its own credential lifecycle.
