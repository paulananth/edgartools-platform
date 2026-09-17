# Clean MDM identity and relationship model

Status: target design. Company/Person separation and governed profiles are
user-directed; additional representations await the Wayfinder policy gate.

## Identity and profile boundaries

| Identity kind | Meaning | Governed profiles / boundary |
| --- | --- | --- |
| Company | An accepted company legal identity | Adviser, Audit Firm, and Fund where legal-form evidence supports Company. Profiles share its identity ID. A name ending in “fund” is insufficient. |
| Person | A natural person | Adviser where individually registered. Never merge with a Company, employer, sole-proprietor business, or similarly named person through a role. |
| Security | A distinct financial instrument | Identifier history and typed issuer links. Neither an ISIN nor a CUSIP is a Company attribute. Issuer plus title alone is review evidence. |
| Branch | A separately identified branch establishment | Distinct ID, including where it is not a separate legal person. `IS_INTERNATIONAL_BRANCH_OF` retains the separately accepted head office. |
| Government Entity | An accepted government body | Distinct ID and governed government identifiers; not a Company. |
| International Organization | An organization whose accepted category supports this representation | Common registry kind and common legal-evidence fields; no dedicated domain table, consistent with the earlier accepted boundary. Preserve source classification history. |
| Market/Venue | A market or trading venue identified within an approved MIC contract | Distinct ID and dated operator relationship; never collapse venue and operator. Operating/segment MIC relationships are venue hierarchy, not corporate ownership. |
| Fund Structure | A supported non-company fund arrangement | `fund_structure` kind, governed Fund profile, explicit form such as trust, contractual fund, umbrella, or subfund. Structural level and legal personality remain separate assertions; unknown form stays deferred. |

A profile is a dated, evidence-backed capability or regulated registration,
not another identity. Profile key includes identity, role, authority,
registration identifier, and jurisdiction where applicable; multiple
registrations may coexist. Closing a profile does not retire its holder.

Company and Person are the first supported identities. Other kinds are added
only with validated identity and consumer contracts. “Registered in GLEIF” is
not blanket permission to choose Company. A sole proprietor does not establish
Person-to-business identity without an approved boundary and source evidence.
Unsupported evidence is stored with a reason and owning consumer, not dropped
or converted to a generic placeholder.

Fund profiles attach to Company or Fund Structure, never to a Security merely
because the security is a fund share. A share class is an instrument only
when the approved instrument contract proves that meaning. PFID, LEI, SEC
series/class IDs, fund legal personality, and management relationships retain
their own namespaces; similarly named umbrella/subfund/share-class records
are not automatically the same identity.

## Source classification and identity

Store source category, asserted legal form, and inferred local identity kind
separately. The kind assignment retains its rule and evidence. A correction
that changes kind goes to review and bounded rebuild; it cannot use an entity
merge to bypass the incompatible-kind veto.

An identifier has authority, namespace, normalized value, scope/jurisdiction,
valid interval, and source assertion. Exclusivity is policy-specific. An
identity may legitimately have identifiers from different namespaces; two
different concurrently valid values in a single-valued authoritative namespace
are a conflict. Identifier reuse or succession does not establish sameness.

## Relationship contracts

All intervals are half-open `[valid_from, valid_to)`; missing upper bound
means open. Unknown lower bounds are explicit uncertainty, never ingest time.
An unknown date cannot satisfy an acceptance gate requiring dated evidence.
Source validity and system-recorded time are separate.

| Relationship | Permitted endpoints | Required distinction |
| --- | --- | --- |
| `AUDITED_BY` | Company to Company carrying applicable Audit Firm profile | Fiscal period / engagement interval and filing provenance; no timeless auditor attribute replacing engagements |
| Adviser registration/association | Company or Person to its governed Adviser profile; associations to separately evidenced parties | Same-ID profile membership replaces `IS_ENTITY_OF` / `IS_PERSON_OF`; employment/association is a real edge, not a merge |
| `ISSUED_BY` | Security to accepted Company, Fund Structure, Government Entity, or International Organization | Endpoint kind must have its consumer enabled. Branch and Person issuer publication stay deferred pending explicit authority. |
| Ownership parent | Accepted legal identities supported by the source contract | Ownership percentage/control evidence, distinct from accounting consolidation; multiple owners are possible |
| Accounting direct parent | Supported legal identities | Accounting standard/scope, reporting interval and authority; at most one selected direct parent in the same scope/time, otherwise conflict |
| Reported ultimate parent | Supported legal identities | Exact source claim, including source status and exceptions; never overwrite with a derived traversal |
| Calculated ultimate parent | Supported legal identities | Derived from accepted direct-parent edges at an explicit watermark under a versioned algorithm; retain full path and unavailable/cycle states |
| `EMPLOYED_BY` / insider association | Person to Company | Source-reported office/role and valid dates; holdings do not imply employment |
| Holdings | Accepted Person, Company, or Fund Structure to Security | Source form, owner/manager capacity, reporting period, units and quantities; 13F manager is not automatically beneficial owner |
| `MANAGES_FUND` | Company/Person with Adviser profile to Company/Fund Structure with Fund profile | SEC ADV assertion; retain reporting adviser, filing and fund grain |
| GLEIF fund relationships | Typed accepted fund/manager endpoints | Keep `IS_FUND-MANAGED_BY`, `IS_SUBFUND_OF`, `IS_FEEDER_TO` direction and meaning; do not reverse ADV edges as substitutes |
| `IS_INTERNATIONAL_BRANCH_OF` | Branch to accepted head-office identity | Source direction and dates; missing head office remains deferred |
| Venue operator / venue hierarchy | Market/Venue to accepted operator / Market/Venue | MIC semantics and dated mapping; not legal ownership |

Cycle checks operate per hierarchical relationship type, scope, and overlapping
valid time, not on the union of all edges ever observed. Ownership cycles may
be legitimate cross-holdings: detect and report them, and prevent a tree-based
ultimate-parent calculation from claiming a result; do not erase valid source
ownership assertions. Accounting-parent and venue/fund/branch hierarchy cycles
block the affected hierarchy projection. Self-links, invalid intervals,
unaccepted endpoints, and conflicting selected parents retain diagnostic
evidence and do not become publishable edges.

## Migration consequences

Rebuild from approved pinned source assertions, not from presumed-clean legacy
master rows. Legacy IDs become an explicitly verified, versioned crosswalk to
new identities and profiles; ambiguous mappings remain unresolved. Two legacy
role IDs mapping to one Company is expected, but must have identity evidence.
Legacy-to-new row-count equality is therefore not an identity acceptance test.

Current entry points and the mastering → relationship derivation → publication
order remain the orchestration interface. Every adapter submits evidence to
the Merge Stage; no bulk writer, relationship stub helper, steward, or repair
command may retain a second master-state mutation path.
