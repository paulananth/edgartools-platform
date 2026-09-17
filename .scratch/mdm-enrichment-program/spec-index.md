# MDM Enrichment Program specification index

This index assigns one future specification owner to every program surface.
Paths are planned destinations; they are not created until the owning decision
work is complete.

| Workstream | Class | Owner role | Terminal outcome | Future specification |
| --- | --- | --- | --- | --- |
| Shared enrichment foundation | Mandatory | Data Platform owner | Verified foundation, then production evidence | `docs/specs/mdm-enrichment/shared-foundation.md` |
| Company legal entity | Mandatory | Company MDM owner | Verified consumer and production evidence | `.scratch/gleif-company-augmentation/spec.md` |
| Security and issuer | Mandatory | Security MDM owner | Verified consumer and production evidence | `docs/specs/mdm-enrichment/security-issuer.md` |
| Fund relationships | Mandatory | Fund MDM owner | Verified consumer and production evidence | `docs/specs/mdm-enrichment/fund-relationships.md` |
| Branch legal entity | Mandatory | Branch MDM owner | Verified consumer and production evidence | `docs/specs/mdm-enrichment/branch.md` |
| Adviser/Audit Firm | Mandatory | Adviser and Audit Firm MDM owners | Verified consumers and production evidence | `docs/specs/mdm-enrichment/adviser-audit-firm.md` |
| Government entity | Mandatory | Government Entity MDM owner | Verified consumer and production evidence | `docs/specs/mdm-enrichment/government-entity.md` |
| International organization classification | Mandatory route | Shared Foundation owner | Verified common-entity projection and production evidence | Owned by Shared Foundation spec |
| Sole proprietor/Person boundary | Mandatory decision | Data Governance and Privacy owners | Verified publish or captured-only decision | `docs/specs/mdm-enrichment/sole-proprietor.md` |
| Market/Trading Venue | Mandatory | Market/Venue MDM owner | Verified consumer and production evidence | `docs/specs/mdm-enrichment/market-venue.md` |
| ISIN mapping | Mandatory | Security MDM owner | Verified within Security consumer | Owned by Security spec |
| BIC mapping | Mandatory | Branch and Adviser MDM owners | Verified within owning consumers | Owned by Branch/Adviser specs |
| MIC mapping | Mandatory | Market/Venue MDM owner | Verified within Market/Venue consumer | Owned by Market/Venue spec |
| OpenCorporates mapping | Mandatory | Company MDM owner | Verified within Company consumer | Owned by Company spec |
| QCC mapping | Mandatory | Company/Government MDM owners | Verified within owning consumers | Owned by Company/Government specs |
| GEM mapping | Mandatory | Company/Government MDM owners | Verified within owning consumers | Owned by Company/Government specs |
| S&P CIQ mapping | Conditional | Source Evaluation + Company MDM owners | Adopt, trigger-bound defer, or reject | `docs/specs/mdm-enrichment/conditional/sp-ciq.md` after adoption |
| Market data | Conditional | Source Evaluation + Security/Market owners | Adopt, trigger-bound defer, or reject | `docs/specs/mdm-enrichment/conditional/market-data.md` after adoption |
| Sanctions | Conditional | Source Evaluation + Data Governance owners | Adopt, trigger-bound defer, or reject | `docs/specs/mdm-enrichment/conditional/sanctions.md` after adoption |
| ESG | Conditional | Source Evaluation + Company MDM owner | Adopt, trigger-bound defer, or reject | `docs/specs/mdm-enrichment/conditional/esg.md` after adoption |
| Credit | Conditional | Source Evaluation + Company/Security owners | Adopt, trigger-bound defer, or reject | `docs/specs/mdm-enrichment/conditional/credit.md` after adoption |
| Other commercial company | Conditional | Source Evaluation + Company MDM owner | Adopt, trigger-bound defer, or reject per source | `docs/specs/mdm-enrichment/conditional/commercial-company.md` after adoption |
| Production rollout | Cross-cutting | Release Engineering + Release Owner | Consumer-specific GO or NO-GO | `docs/specs/mdm-enrichment/production-rollout.md` |
| Operations and stewardship | Cross-cutting | Data Operations + Stewardship owners | Operational acceptance per consumer | `docs/specs/mdm-enrichment/operations.md` |
| Retention and cost | Cross-cutting | Cost owner + Retention operator | Budget and retention acceptance per consumer | `docs/specs/mdm-enrichment/retention-cost.md` |
| Program verification | Cross-cutting | Independent verifier + Release Owner | Enrichment Program Complete or evidenced gaps | `docs/specs/mdm-enrichment/program-verification.md` |

## Specification contract

Every consumer specification must define source authority, accepted identity
evidence, source and MDM schemas, temporal behavior, conflict and review states,
replay and recovery, observability, security, retention, costs, migration and
rollback, tests, release gates, and explicit non-goals. It must cite the owning
workstream and may not silently broaden another consumer's domain.
