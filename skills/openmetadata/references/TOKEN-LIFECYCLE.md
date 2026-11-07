# Token issuance and lifetime

The local service reports OpenMetadata 2.0.2. Use version-specific evidence
before creating or revoking a writable token.

## Supported authentication in this repository

The existing login flow uses `POST /api/v1/users/login` and returns a short-lived
`accessToken`; the local account token expires within an hour. The private-shell
refresh procedure is in [OpenMetadata](../SKILL.md#local-server); this login
token is not an eight-day personal access token (PAT).

Keep credentials and returned tokens in the private runtime environment. Never print them or save them in the repository.

## Longer-lived writable tokens

OpenMetadata's [v2.0.x authentication guide](https://docs.open-metadata.org/v2.0.x/api-reference/authentication)
documents PAT creation from a user's profile. A PAT inherits that user's
permissions, accepts an expiration date, and cannot be retrieved after creation.
The guide does not document a PAT creation API/CLI, the expiration-date boundary
semantics, or a revocation API.

The guide documents bot tokens separately: they inherit the bot's role. The
[v2.0.x JWT guide](https://docs.open-metadata.org/v2.0.x/deployment/security/enable-jwt-tokens)
describes bot token creation and revocation in the OpenMetadata UI, not through
a supported API or CLI.

This repository requires OpenMetadata administration through APIs and CLI, not
browser or UI automation. No supported 2.0.2 API/CLI contract for creating an
eight-day writable token is established here. Do not guess an endpoint, treat a
short-lived login token as an eight-day token, or use the UI as a fallback.
Report the missing API/CLI capability and stop before issuance. If an API/CLI
path becomes available, verify its 2.0.2 request schema, exact expiration
semantics, and effective principal permissions before use; keep the returned
secret outside the repository and do not print it.
