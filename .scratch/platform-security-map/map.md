# Which gaps to close before production changes

## Destination

Decide which security and architecture gaps to close, and in what order, before anyone changes production. The way is clear when each open lead is either an owner-observed fact or an explicit decision, and no production change is waiting on an unstated choice.

## Notes

Audit run `~/security-audit-skill/edgartools-platform/run-1`, source revision `6a272d4dfa90a1d250821b2d10e0af69411eb56c`. Profile quick. No confirmed finding. This map is charted on `2291ea557`, which is later than that revision. Re-check line numbers before editing code.

Do not call AWS, Snowflake, GitHub's API for this repo, or a data provider to resolve a ticket. Owner checks are read-only and are written so the operator runs them.

Skills for a later session: grilling and domain-modeling on every grilling ticket. Do not edit `CONTEXT.md` or an ADR from this map.

## Decisions so far

- [What GitHub documents as the default token for a workflow with no permissions block](issues/01-github-token-default.md): omitting `permissions` uses the account default (new personal repos and new orgs: read on `contents` and `packages` only); a fork pull request's `GITHUB_TOKEN` is read-only unless the documented write-token setting is on.

## Not yet specified

- Whether the Rust source engine needs a bounds review. The quick audit deferred it.
- Whether `file://` artifact writes need a directory jail. The quick audit treated the operator as the same principal and deferred the unit.
- Whether capture prefix matching should require a trailing delimiter. Shipped prefixes already end in `/`, and the URL author is the operator.
- Whether the example dashboard should quote database and schema identifiers. The operator who sets them already runs the process.
- Whether Actions should pin digests. No job in the audited workflow publishes.

## Out of scope

- Implementing an export writer, narrowing IAM, or editing the workflow. Those start only after this map's decisions.
- Live probes, secret reads, and provider requests.
