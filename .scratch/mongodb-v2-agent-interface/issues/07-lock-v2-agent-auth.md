# Lock how v2 agents authenticate to Atlas

Type: grilling
Status: resolved
Blocked by: 05

## Question

How do internet agents authenticate to v2 Atlas?

ADR 0001 defers product OAuth; Atlas still requires a database user and
an IP access list. Options at minimum: one read-only DB user in the
connection string; per-agent users; a later pluggable access layer in
front of Mongo (HTTPS/OAuth) with Atlas private to the publisher.

Do not provision Atlas in this ticket. Network allowlist (`0.0.0.0/0`
vs agent IPs) is ticket 05; this ticket is identity and credentials.

## Comments

- 2026-09-11 Q1 accepted **A**: One read-only SCRAM database user for
  internet agents; separate write user for the publisher; product OAuth
  later without changing document shape. Atlas plugin OAuth is operator
  tooling, not v2 trading-agent auth.

## Answer

Internet agents authenticate with **one read-only SCRAM database user**
in the `mongodb+srv` connection string (TLS already required; IP list
`0.0.0.0/0`). The publisher uses a **separate write user**. Product
OAuth stays deferred (ADR 0001 Deferred Access Control) and must not
change Decision Feature or bundle shape. The `mongodb-atlas` plugin’s
Atlas OAuth is for this coding agent managing Atlas, not for trading
agents.
