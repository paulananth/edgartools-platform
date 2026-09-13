# Ticket 04 accounting-parent and exception evidence

Date: 2026-09-12
Inputs: fixed GLEIF 2026-09-11 16:00 UTC relationship and reporting-exception
Golden Copies; 308 accepted Company-to-LEI links from Ticket 02.

## Result

Thirty accepted companies have current GLEIF accounting-consolidation
relationship evidence: 23 have both direct and ultimate records and seven have
an ultimate record only. The existing frozen MDM parent/subsidiary signal was
zero, so all 30 are additive evidence for this cohort. This does not mean all
30 can immediately publish MDM edges: only two child LEIs and two parent LEIs
are accepted local cohort identities, yielding three typed relationship
records. The other parent endpoints remain source evidence pending independent
identity/domain resolution.

| Company evidence pattern | Count |
| --- | ---: |
| Direct and ultimate relationship | 23 |
| Ultimate relationship plus direct reporting exception | 7 |
| Direct and ultimate reporting exceptions | 255 |
| Neither current relationship nor current exception | 23 |
| **Accepted companies** | **308** |

There are 53 relationship records for accepted child LEIs: 23 direct and 30
ultimate. All have `RelationshipStatus=ACTIVE`; 48 registrations are
`PUBLISHED` and five are `LAPSED`. Lapsed registration is retained separately
from relationship status and is not rewritten as an inactive relationship.
All 53 end nodes are LEIs, representing 28 unique parent LEIs. No accepted
child/type has duplicate current relationship records.

The 517 reporting-exception records cover 262 accepted child LEIs: 262 direct
and 255 ultimate. Reason occurrences are:

| Reason | Occurrences |
| --- | ---: |
| `NON_CONSOLIDATING` | 194 |
| `NO_KNOWN_PERSON` | 194 |
| `NATURAL_PERSONS` | 54 |
| `NON_PUBLIC` | 50 |
| `NO_LEI` | 25 |

No child/type has both a current relationship and current exception. Reasons
are type-scoped and may differ between direct and ultimate categories. They are
not affirmative proof of no legal parent, no owner, or no controlling party.
The 23 companies with neither record remain unknown under this publication.

## Reproducibility

The relationship scan examined all 487,721 fixed source records and retained
2,987 records touching an accepted LEI as either endpoint. Its retained
artifact SHA-256 is
`8ae9395a0283bc523d362bbe9473d7c83d28ee275b592226eab6f0c88c9abba7`.
Filtering to accepted start nodes produces the 53 child relationship records
reported above.

The exception scan examined all 6,351,397 fixed source records and retained 517
records covering accepted LEIs. Its SHA-256 is
`f047d13df414d69a0f7f04f55b3472a1576eb2206c75f3ab3677a8aae015405c`.
The machine-readable aggregate is
[`04-parent-exception-summary.json`](04-parent-exception-summary.json).

## Specification consequence

The first Company consumer should capture all direct/ultimate records and
exceptions, but publish a typed MDM edge only when both endpoint identities are
accepted Companies. Missing endpoint resolution is a blocked evidence state,
not permission to manufacture a Company. Missing relationship and exception
records remain unknown. Direct and ultimate types stay distinct from each
other and from SEC `HAS_PARENT_COMPANY`.
