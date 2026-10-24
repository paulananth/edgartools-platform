# What GitHub documents as the default token for a workflow with no permissions block

Type: research
Status: resolved
Blocked by:

## Question

What do GitHub's own docs say the `GITHUB_TOKEN` can do when a workflow omits `permissions`, for a pull request from the same repository and for a pull request from a fork? Cite the documentation. Do not read this repository's live settings and do not call GitHub for this repo.

## Checklist

- [x] Read the current GitHub docs on default workflow permissions and forked pull requests. 2026-10-23 20:35 ET, GitHub docs pages cited in the research note.
- [x] Write the cited answer on this ticket. 2026-10-23 20:35 ET, `research/github-actions-token.md`.
- [x] Learning → skill: none. 2026-10-23 20:35 ET. No skill changed.

## Answer

Omitting `permissions` uses the enterprise, organization, or repository default. It is not `permissions: {}`. For a new personal repository or a new organization, GitHub's repository and organization docs say that default is read access only for `contents` and `packages`. A same-repository pull request is not a fork, so it keeps that default (or the permissive read-and-write-for-all-permissions setting, if that is what the account selected). A pull request from a fork gets a read-only `GITHUB_TOKEN`: documented writes are dropped to read unless **Send write tokens to workflows from pull requests** is selected. `pull_request_target` is excluded from that downgrade. Cited note: [github-actions-token.md](../research/github-actions-token.md).
