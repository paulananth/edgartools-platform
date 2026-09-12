# Lock Atlas tier and public network for v2 agents

Type: grilling
Status: resolved
Blocked by: 01

## Question

Does v2 target Atlas Free (M0: 512 MB, public hostname, IP allowlist)
or a paid cluster? If Free, is the agent path `0.0.0.0/0` plus DB user,
or allowlisted agent IPs only?

M0 has no peering or private endpoints. A dedicated public IPv4 is not
an Atlas feature; the product is a `mongodb+srv` hostname.

## Comments

- 2026-09-11 Q1 accepted **A**: v2 starts on Atlas Free (M0). Paid only
  if later density, ops/s, or transfer require it.
- 2026-09-11 Q2 accepted **A**: Internet agents reach M0 via `0.0.0.0/0`
  plus TLS plus a database user. Atlas warns and emails on `/0`. Not
  IP-allowlist-only. Not publisher-only. Auth identity is ticket 07.

## Answer

v2 starts on **Atlas Free (M0)**. A paid cluster is not a prerequisite;
upgrade only if later density, ops/s, or 10 GB/week transfer require it.

Internet agents use the public `mongodb+srv` hostname with the IP access
list set to **`0.0.0.0/0`**, TLS required, and a database user (ticket
07). No peering or PrivateLink on M0. Do not hardcode cluster IPs.
