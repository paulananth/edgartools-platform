# Decide how a Source Contract is registered and run

Type: grilling
Status: resolved (2026-09-21)
Blocked by: 01

## Question

Check 1 fails if a new source needs its own orchestration stage. Decide:

- where Source Contracts live (`sources/<name>/`?) and how the engine
  discovers them;
- how a contract version is registered (alongside Clean MDM's source
  registry and `store.register_policy`, not a competing registry);
- how one generic stage runs every registered contract over new Bronze
  Artifacts and publishes to Clean MDM as a pinned source publication;
- what the one local command (`source check`) does and does not share with
  that stage.

## Decisions in progress

- **Q1 Master copy (2026-09-21, operator):** **the database is the master**
  (option b), not git files. Needs a way to store and initialize contracts
  (Q2). Custom-step code and fixtures necessarily remain files; the stored
  version records their digests.
- **Q3 Lifecycle (2026-09-21, operator):** draft → proven → active →
  retired, authored by an agent.
  - **Proving Runs execute in a separate database, `rules_db`** (option a) — never
    against production identities.
  - **Activation (option z):** the agent may activate changes that only add
    data; any version that can **bind or merge identities** needs human
    approval, and **the agent must explicitly ask the operator for approval
    before making it final** — approval is never inferred. The approver,
    time and exact digest approved are recorded with the proof.
  - Term: "golden merge rule" would collide with GLEIF's Golden Copy and
    "golden record"; the policy language's word is **active**.
- **Q2 Storage and initialization (2026-09-21, operator: yes):**
  - **`rules_db` is the master store**: our own Postgres, separate from
    Clean MDM's `mdm_v2`, holding every Source Contract and Mastering Policy
    version (draft, proven, active, retired), proofs, approvals and throwaway
    Proving Run merges. **Local first**; a hosted move later does not change the
    design.
  - Writes only through commands, never raw SQL: `source save <file.yaml>`
    validates and stores an immutable new draft; `source export <name>
    <version>` writes YAML back out for reading and local tests.
    Initialization is `source save` over a folder.
  - **Activation is a hand-off**: the active version is registered into
    Clean MDM through its own `register_policy` / `register_dataset`.
    Production merges read only `mdm_v2`, pinned by digest; `rules_db` is
    never on the production path. Version 2 of a Dataset Contract needs
    Codex's versioning fix (ticket 08 handover item 4).
- **Term (2026-09-21, operator: yes):** **Proving Run** (the run) and
  **proven** (its passing state) replace "trial". Lifecycle: draft → proven
  → active → retired. A failed Proving Run leaves the version draft; proof
  is pinned to the batch hash it ran on. Added to `CONTEXT.md`.
- **Q4 Running (2026-09-21, agreed):** one generic command for every
  source — `source run [--source <name>]` finds unparsed Bronze Artifacts of
  the contract's declared family (skip key `(artifact sha256, contract
  digest)`), parses into silver through the declared `read`/`silver`,
  publishes a pinned source publication to Clean MDM, fails closed on
  unknown errors and counts rejects. What triggers it is out of scope.
  `source prove <name|file>` is the Proving Run: the same engine code over
  fixtures and a local batch, merging into the Rules Database, network
  blocked. (Replaces the earlier name `source check`.)

## Answer

**The Rules Database is the master; Clean MDM is what production reads.**
An agent writes versions into the Rules Database only through `source save`
(validated, immutable drafts; `source export` gives YAML back), proves them
with `source prove` (a Proving Run, never against production identities),
and activates them by registering into Clean MDM through `register_policy` /
`register_dataset`. Versions that only add data may be activated by the
agent; versions that can bind or merge identities need a Rule Activation
Approval the agent explicitly asks for, recorded with approver, time and
digest. `source run` is the one production command for every source.
Lifecycle: draft → proven → active → retired. Custom code and fixtures stay
files whose digests the version records.
