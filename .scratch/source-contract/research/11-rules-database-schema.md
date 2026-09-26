# Research 11: the Rules Database schema

Ticket: [11](../issues/11-research-the-rules-database-schema.md).
Date: 2026-09-26. Research only: every recommendation here is a proposal
for the operator. Nothing here is a decision.

**Outcome (2026-09-26):** the operator chose files in git plus one table
(`rules.rule_version`), not the two tables proposed here. See the ticket's
Answer.

## 1. Answer first

- **Two tables:** `version` stores each version once; `event` stores its proofs, approvals, activations and retirements.
- **Nothing is updated.** A version's state is derived from its events by a view. It is never stored.
- **One active version per name:** each activation names the one it replaces, and a partial unique index allows one successor.
- **Each body is stored once**, as canonical JSON text. The database checks its SHA-256.
- **Not one table:** events then lose their foreign key to the version (tested). **Not normalized tables:** that means 19 tables.
- Normalized tables also need a migration per new key, and the bodies gained 9 keys in 7 days (§3.5).
- **Cost:** a new MDM field, source or rule family needs no migration. A new document kind needs a one-line CHECK change.
- **A separate database, not a schema:** production is not given a connection to it.
- **Clean MDM keeps less:** `mdm_v2.dataset` shrinks to a list of source codes after its five readers move (one Codex migration).
- **Biggest open question:** where production `source run` gets `read`, `silver` and `custom.py` (§7, question 1).
- The final DDL ran on PostgreSQL 16.15 in a throwaway container. Every step and refusal was tested (§4.7).

## 2. Constraints carried in

These are fixed by earlier operator decisions. This research does not
reopen them.

- The Rules Database is its own Postgres, separate from `mdm_v2`, and local
  first (ticket 06 Q2, `issues/06-…md:37-42`; spec §4.1,
  `docs/specs/source-contract/spec.md:58-66`).
- Each version is canonical JSON with its SHA-256, and a stored version
  never changes (`spec.md:64-65`).
- The lifecycle is draft → proven → active → retired. A failed Proving Run
  leaves the version in draft and is kept as a record (`spec.md:77-91`).
- A proof is pinned to the batch hash it ran on (`spec.md:781-786`). A Rule
  Activation Approval records the approver, the time and the exact digest.
  It is needed only for versions that can bind or merge identities
  (`spec.md:92-102`; `CONTEXT.md:173-175`).
- Custom code and fixtures stay files, and the version records their digests
  (`spec.md:66-68`).
- Production never reads the Rules Database. Activation hands the Dataset
  Contract to `register_dataset` and the Mastering Policy to
  `register_policy` (`spec.md:69-72`; ticket 06 `:47-51`).
- Writes happen only through commands, never raw SQL (ticket 06 `:43-46`).
- Operator direction, 2026-09-26: a lean, clean, KISS MDM; sources fully
  decoupled; new MDM fields easy to add; remove a layer rather than tune it;
  no extra work.

Two facts from the code shape the design:

- **Today's policy body holds its own approvals.** `check_policy` refuses an
  automatic rule whose proof lacks `approved_by`, `approved_at` and `reason`
  (`edgar_warehouse/mdm/clean/activation.py:278-279`). It also refuses an
  Identifier Contract without them (`activation.py:438-443`). So the digest
  a person approves (D) is not the digest Clean MDM registers (D′). See §7,
  question 3.
- **Spec §23 is partly out of date.** It says a second version of a
  contract needs a new `source_code` (`spec.md:998`). Migration 031
  (2026-09-23, after the spec) added mapping versions. A corrected mapping
  now becomes a new reading of the same source
  (`edgar_warehouse/mdm/migrations/031_clean_mdm_mapping_version.sql:1-12`).
  A new `source_code` is still needed only when a protected part changes:
  `record_key`, `publication_key`, or the adapter's `record_key`,
  `record_key_format`, `identifiers` or `identifier_formats`
  (`edgar_warehouse/mdm/clean/store.py:343-349`, `:393-413`).

## 3. The three shapes

The core tension: a version body never changes, but its lifecycle state
does. A single table must either UPDATE a row, which breaks immutability, or
append a row per state, which risks storing the body twice. Clean MDM has
that defect today (§6).

### 3.1 Shape 1: one append-only table

The body appears only on the `saved` row. Every other row is an event about
it. Tested on PostgreSQL 16.15.

```sql
CREATE TABLE s1.rule_row (
    row_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind        text NOT NULL CHECK (kind IN ('source_contract', 'mastering_policy')),
    name        text NOT NULL,
    digest      text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
    row_type    text NOT NULL CHECK (row_type IN ('saved', 'proved', 'proof_failed', 'approved', 'activated', 'retired')),
    body        text,
    batch_hash  text CHECK (batch_hash ~ '^[0-9a-f]{64}$'),
    supersedes  bigint REFERENCES s1.rule_row (row_id),
    change      text CHECK (change IN ('adds_data', 'binds_or_merges')),
    detail      jsonb NOT NULL DEFAULT '{}',
    actor       text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((row_type = 'saved') = (body IS NOT NULL)),
    CHECK (body IS NULL OR digest = encode(sha256(convert_to(body, 'UTF8')), 'hex')),
    CHECK ((row_type IN ('proved', 'proof_failed')) = (batch_hash IS NOT NULL)),
    CHECK ((row_type = 'activated') = (change IS NOT NULL))
);
-- One body per digest.
CREATE UNIQUE INDEX rule_row_one_body ON s1.rule_row (digest) WHERE row_type = 'saved';
-- One active per name, as in shape 2.
CREATE UNIQUE INDEX rule_row_one_successor ON s1.rule_row (kind, name, supersedes)
    NULLS NOT DISTINCT WHERE row_type IN ('activated', 'retired');
-- "An event names a saved version" cannot be a foreign key:
ALTER TABLE s1.rule_row ADD FOREIGN KEY (digest) REFERENCES s1.rule_row (digest);
-- ERROR:  there is no unique constraint matching given keys for referenced table "rule_row"
```

The last statement fails because a foreign key can only reference "a primary
key … a unique constraint, or … a non-partial unique index" (PostgreSQL 16,
§5.4). The alternative, repeating the body on every state row, stores it up
to four times. That is the `dataset`/`dataset_mapping` defect again.

### 3.2 Shape 2: one immutable versions table and one append-only events table

The full DDL is the recommended schema in §4.1. In short: `version(digest
PK, kind, name, body)` and `event(event_id, digest → version, event,
batch_hash, proof_event, approval_event, supersedes, change, detail, actor,
recorded_at)`. Two views derive the current pointer and each version's
state.

### 3.3 Shape 3: normalized tables for each kind

The columns follow today's bodies: the prototype GLEIF contract
(`.scratch/source-contract/prototype/sources/gleif/contract.yaml`) and the
company-mastering candidate policy (`git show
origin/claude/company-mastering-05-proving-run:.scratch/company-mastering/research/05-candidate-policy.json`).
That policy alone has 116 distinct key paths, nested up to six levels. Tested
on PostgreSQL 16.15: all 19 tables are created.

```sql
-- Source Contracts
CREATE TABLE s3.source (source_code text PRIMARY KEY);
CREATE TABLE s3.source_version (
    digest        text PRIMARY KEY,
    source_code   text NOT NULL REFERENCES s3.source,
    label         text NOT NULL,
    bronze_family text NOT NULL,
    read          jsonb NOT NULL,          -- readers, tables, columns: primitive calls
    silver        jsonb NOT NULL,
    lookups       jsonb,
    checks        jsonb,
    tests         jsonb NOT NULL,
    gate          jsonb,
    requires      text[],
    custom_sha256 text,
    saved_by      text NOT NULL,
    saved_at      timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE s3.fixture (
    version_digest text REFERENCES s3.source_version,
    path           text,
    sha256         text NOT NULL,
    PRIMARY KEY (version_digest, path)
);
CREATE TABLE s3.dataset_contract (
    version_digest       text PRIMARY KEY REFERENCES s3.source_version,
    silver_table         text NOT NULL,
    provider             text NOT NULL,
    family               text NOT NULL,
    schema_version       text NOT NULL,
    record_key           text NOT NULL,
    publication_key      text NOT NULL,
    effective_time       text NOT NULL,
    semantics            text NOT NULL,
    completeness         text,
    publication_families text[],
    publication_contract jsonb,
    nonblocking_deferred_reasons text[]
);
CREATE TABLE s3.adapter (
    version_digest           text PRIMARY KEY REFERENCES s3.dataset_contract,
    adapter_version          text NOT NULL,
    kind                     text,
    kind_field               text,
    kind_values              jsonb,
    classification           text,
    probable_kind_values     jsonb,
    record_key               text[] NOT NULL,
    record_key_format        text,
    field_shape              text,
    source_record_provenance boolean,
    retain_deferred          boolean,
    provenance               jsonb
);
CREATE TABLE s3.adapter_identifier (
    version_digest text REFERENCES s3.adapter,
    namespace      text,
    column_name    text NOT NULL,
    format         text,
    PRIMARY KEY (version_digest, namespace)
);
CREATE TABLE s3.adapter_field (
    version_digest text REFERENCES s3.adapter,
    mdm_field      text,
    column_name    text NOT NULL,
    PRIMARY KEY (version_digest, mdm_field)
);
CREATE TABLE s3.adapter_profile (
    version_digest text REFERENCES s3.adapter,
    position       int,
    role           text NOT NULL,
    authority      text NOT NULL,
    registration   text NOT NULL,
    valid_from     text NOT NULL,
    valid_to       text,
    jurisdiction   text,
    fields         jsonb,
    PRIMARY KEY (version_digest, position)
);
CREATE TABLE s3.adapter_relationship (
    version_digest text REFERENCES s3.adapter,
    position       int,
    type           text NOT NULL,
    target_key     text[] NOT NULL,
    target_source  text NOT NULL,
    valid_from     text NOT NULL,
    valid_to       text,
    scope          text,
    properties     jsonb,
    PRIMARY KEY (version_digest, position)
);

-- Mastering Policies
CREATE TABLE s3.policy_version (
    digest             text PRIMARY KEY,
    label              text,
    required_consumers text[] NOT NULL,
    saved_by           text NOT NULL,
    saved_at           timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE s3.policy_kind (
    policy_digest   text REFERENCES s3.policy_version,
    kind            text,
    kind_version    text,
    default_sources text[],
    default_allow_unknown_effective boolean,
    bars            jsonb,
    lists           jsonb,
    normalizers     jsonb,
    PRIMARY KEY (policy_digest, kind)
);
CREATE TABLE s3.field_rule (
    policy_digest           text,
    kind                    text,
    field                   text,
    sources                 text[] NOT NULL,
    allow_unknown_effective boolean,
    PRIMARY KEY (policy_digest, kind, field),
    FOREIGN KEY (policy_digest, kind) REFERENCES s3.policy_kind
);
CREATE TABLE s3.identifier_contract (
    policy_digest           text,
    kind                    text,
    namespace               text,
    authority               text NOT NULL,
    claim_forward           int NOT NULL,
    claim_reverse           int,
    normalizer              text NOT NULL,
    compatibility_field     text NOT NULL,
    compatibility_predicate text NOT NULL,
    sources                 text[] NOT NULL,
    tolerance_unit          text NOT NULL,
    tolerance_max_per_10k   numeric NOT NULL,
    warm_up_decisions       int NOT NULL,
    corpus_sha256           text NOT NULL,
    approved_by             text,
    approved_at             timestamptz,
    reason                  text,
    PRIMARY KEY (policy_digest, kind, namespace),
    FOREIGN KEY (policy_digest, kind) REFERENCES s3.policy_kind
);
CREATE TABLE s3.rule (
    policy_digest      text,
    kind               text,
    rule_id            text,
    rule_version       text,
    family             text NOT NULL,
    source             text,
    holder_source      text,
    on_no_match        text,
    applies_to_verdict text,
    emits              text,
    when_clause        jsonb,               -- primitive calls with open-ended args
    steps              jsonb,
    PRIMARY KEY (policy_digest, kind, rule_id, rule_version),
    FOREIGN KEY (policy_digest, kind) REFERENCES s3.policy_kind
);
CREATE TABLE s3.automatic_rule (
    policy_digest text REFERENCES s3.policy_version,
    kind          text,
    family        text,
    rule_id       text,
    rule_version  text,
    verdict       text NOT NULL,
    activation    text NOT NULL,
    proof         jsonb,
    PRIMARY KEY (policy_digest, kind, family, rule_id, rule_version)
);

-- Lifecycle, shared by both kinds: each row names one of two parents.
CREATE TABLE s3.proving_run (
    run_id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_version_digest text REFERENCES s3.source_version,
    policy_version_digest text REFERENCES s3.policy_version,
    batch_hash            text NOT NULL,
    passed                boolean NOT NULL,
    engine                text NOT NULL,
    result                jsonb NOT NULL,
    runner                text NOT NULL,
    ran_at                timestamptz NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(source_version_digest, policy_version_digest) = 1)
);
CREATE TABLE s3.approval (
    approval_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_version_digest text REFERENCES s3.source_version,
    policy_version_digest text REFERENCES s3.policy_version,
    approved_by           text NOT NULL,
    approved_at           timestamptz NOT NULL,
    CHECK (num_nonnulls(source_version_digest, policy_version_digest) = 1)
);
CREATE TABLE s3.activation (
    activation_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_version_digest text REFERENCES s3.source_version,
    policy_version_digest text REFERENCES s3.policy_version,
    line                  text NOT NULL,     -- source_code, or the policy's name
    supersedes            bigint REFERENCES s3.activation,
    change                text NOT NULL CHECK (change IN ('adds_data', 'binds_or_merges')),
    approval_id           bigint REFERENCES s3.approval,
    clean_mdm             jsonb NOT NULL,
    activated_by          text NOT NULL,
    activated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(source_version_digest, policy_version_digest) = 1)
);
CREATE UNIQUE INDEX activation_one_successor ON s3.activation (line, supersedes) NULLS NOT DISTINCT;
CREATE TABLE s3.retirement (
    activation_id bigint PRIMARY KEY REFERENCES s3.activation,
    why           text NOT NULL,
    retired_by    text NOT NULL,
    retired_at    timestamptz NOT NULL DEFAULT now()
);
-- Plus an append-only trigger on each of the 19 tables.
```

Even so, `read`, `silver`, `tests`, `when_clause`, `steps` and `proof` stay
jsonb. Their arguments are open-ended primitive calls, so normalizing them
would need a table per primitive. The lifecycle tables need two nullable
parents, because one foreign key cannot point at two version tables.
Removing that would need a shared version table, which is shape 2's
`version`.

### 3.4 How each command maps to rows, per shape

| Command | Shape 1 | Shape 2 | Shape 3 |
|---|---|---|---|
| `source save` | 1 `saved` row with the body | 1 `version` row | Source Contract: rows in up to 9 tables (`source` if new, `source_version`, `fixture`×n, `dataset_contract`, `adapter`, `adapter_identifier`×n, `adapter_field`×n, `adapter_profile`×n, `adapter_relationship`×n). Mastering Policy: rows in 6 tables |
| `source prove` | 1 `proved` or `proof_failed` row with `batch_hash` | 1 `event` row, the same | 1 `proving_run` row |
| approve | 1 `approved` row | 1 `event` row | 1 `approval` row |
| activate | 1 `activated` row naming the row it supersedes | 1 `event` row, the same | 1 `activation` row |
| retire (withdraw a source) | 1 `retired` row | 1 `event` row | 1 `retirement` row |
| `source export` | read 1 `saved` row | read 1 `version` row | rebuild the canonical JSON from 6–9 tables, byte for byte, or the digest no longer matches |
| status | a view over one table, filtered by `row_type` | a view over two tables | joins over the lifecycle tables and both version tables |

### 3.5 Scores

| Criterion | 1: one table | 2: versions + events | 3: normalized |
|---|---|---|---|
| Tables | 1 | 2 (plus 2 views) | 19 |
| **A new MDM field** (target: no migration) | none: a key in the body | none: a key in the body | none for a new field row; **a migration** for a new attribute of a field rule |
| **A new source** | rows only | rows only: 1 `version` row plus its events | rows in up to 9 tables; **a migration** if it uses an adapter key the tables lack |
| **A new rule family, or a new key in a policy or adapter** | none | none | **a migration** plus `save`/`export` code. Evidence: 9 new body keys in 7 days (below) |
| **A new document kind** (a third kind besides the two) | one-line CHECK change | one-line CHECK change | new tables, plus a new parent column on `proving_run`, `approval` and `activation` |
| "Current" derived, never stored | yes (view) | yes (view) | yes (activation chain) |
| At most one active per name | partial unique index on the chain | the same index | the same index |
| Any body in two places | no, but only by row-type discipline | **no** | the canonical JSON is not stored, so the database cannot check the digest. Storing it too would keep the body twice |
| An event points at a real version | **cannot be a foreign key** (tested); needs a trigger | composite foreign key | two nullable foreign keys plus a CHECK, per lifecycle table |
| Digest checked by the database | yes, on `saved` rows | yes | no |
| Immutability triggers | 1 table | 2 tables | 19 tables |
| Columns that depend on the row type | almost all | the event columns only | few |

The 9 keys, with their first commits: `publication_contract` (2026-09-20,
`0c1449df`), `nonblocking_deferred_reasons` (09-22, `0971a210`);
`classification`, `bars`, `lists` and `normalizers` (09-23, `197a6aaa`);
`defaults` (09-24, `67ea4672`); `probable_kind_values` (09-25, `a8bfe004`).
Clean MDM's own tables started on 2026-09-19 (`e2807e52`). Found with
`git log -S<key> -- edgar_warehouse/mdm/clean/`.

**Recommendation: shape 2.** It is the only shape that stores each body once
and still lets every event have a foreign key to its version. It also needs
no migration as bodies grow. Shape 1 saves one table, but loses the foreign
key and makes every column conditional. Shape 3 adds a layer that the
operator's direction says to remove.

## 4. Recommended schema

### 4.1 DDL

Ran as written on PostgreSQL 16.15, in a database created with `ENCODING
'UTF8'`.

```sql
-- Rules Database, recommended shape: one immutable table of versions and one
-- append-only table of events. State is derived and never stored.
-- Run as a superuser in a new database created with ENCODING 'UTF8'.
CREATE ROLE rules_owner    NOLOGIN;   -- owns the tables; used only by migrations
CREATE ROLE rules_writer   NOLOGIN;   -- source save, prove, activate, retire
CREATE ROLE rules_approver NOLOGIN;   -- Rule Activation Approvals; people only
CREATE ROLE rules_reader   NOLOGIN;   -- source export, status, review
REVOKE ALL ON DATABASE rules FROM PUBLIC;
GRANT CONNECT ON DATABASE rules TO rules_writer, rules_approver, rules_reader;

CREATE SCHEMA rules AUTHORIZATION rules_owner;
SET ROLE rules_owner;

-- One row per version. The body is the canonical JSON text: the exact bytes
-- the digest covers. (jsonb would reorder keys and drop whitespace.)
CREATE TABLE rules.version (
    digest   text PRIMARY KEY,
    kind     text NOT NULL CHECK (kind IN ('source_contract', 'mastering_policy')),
    name     text NOT NULL CHECK (name ~ '^[a-z0-9][a-z0-9._-]*$'),
    body     text NOT NULL,
    saved_by text NOT NULL DEFAULT session_user,
    saved_at timestamptz NOT NULL DEFAULT now(),
    CHECK (digest = encode(sha256(convert_to(body, 'UTF8')), 'hex')),
    CHECK (jsonb_typeof(body::jsonb) = 'object'),
    -- A Source Contract's name is its `source` key, which becomes Clean MDM's source_code.
    CHECK (kind <> 'source_contract' OR name = body::jsonb ->> 'source'),
    UNIQUE (digest, kind, name)   -- the target of event's foreign key
);

-- One row per thing that happened to a version.
CREATE TABLE rules.event (
    event_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    digest         text NOT NULL,
    kind           text NOT NULL,
    name           text NOT NULL,
    event          text NOT NULL CHECK (event IN ('proved', 'proof_failed', 'approved', 'activated', 'retired')),
    batch_hash     text CHECK (batch_hash ~ '^[0-9a-f]{64}$'),
    proof_event    bigint,       -- the passing proof an approval or activation rests on
    approval_event bigint,       -- the approval an activation rests on
    supersedes     bigint,       -- the pointer event an activation or retirement replaces
    change         text CHECK (change IN ('adds_data', 'binds_or_merges')),
    detail         jsonb NOT NULL CHECK (jsonb_typeof(detail) = 'object'),
    actor          text NOT NULL DEFAULT session_user,
    recorded_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (event_id, digest),
    UNIQUE (event_id, kind, name),
    FOREIGN KEY (digest, kind, name)       REFERENCES rules.version (digest, kind, name),
    FOREIGN KEY (proof_event, digest)      REFERENCES rules.event (event_id, digest),
    FOREIGN KEY (approval_event, digest)   REFERENCES rules.event (event_id, digest),
    FOREIGN KEY (supersedes, kind, name)   REFERENCES rules.event (event_id, kind, name),
    CHECK ((event IN ('proved', 'proof_failed')) = (batch_hash IS NOT NULL)),
    CHECK ((event IN ('approved', 'activated')) = (proof_event IS NOT NULL)),
    CHECK ((event = 'activated') = (change IS NOT NULL)),
    CHECK (change IS DISTINCT FROM 'binds_or_merges' OR approval_event IS NOT NULL),
    CHECK (approval_event IS NULL OR event = 'activated'),
    CHECK (event IN ('activated', 'retired') OR supersedes IS NULL),
    CHECK (event <> 'retired' OR supersedes IS NOT NULL),
    CHECK (event <> 'activated' OR detail ? 'clean_mdm')
);
-- At most one active version per name. Every activation or retirement names
-- the pointer event it replaces (the first names NULL), and no two may name
-- the same one. Concurrent activations race on this index; one loses.
CREATE UNIQUE INDEX event_one_successor ON rules.event (kind, name, supersedes)
    NULLS NOT DISTINCT WHERE event IN ('activated', 'retired');

-- The current pointer event of each name: the one nothing supersedes.
CREATE VIEW rules.head AS
SELECT e.* FROM rules.event e
WHERE e.event IN ('activated', 'retired')
  AND NOT EXISTS (SELECT 1 FROM rules.event n WHERE n.supersedes = e.event_id);

-- Each version's lifecycle state, derived from its events.
CREATE VIEW rules.version_state AS
SELECT v.digest, v.kind, v.name, v.body::jsonb ->> 'version' AS label, v.saved_at,
       CASE
         WHEN h.event_id IS NOT NULL THEN 'active'
         WHEN EXISTS (SELECT 1 FROM rules.event e WHERE e.digest = v.digest AND e.event = 'activated') THEN 'retired'
         WHEN EXISTS (SELECT 1 FROM rules.event e WHERE e.digest = v.digest AND e.event = 'proved') THEN 'proven'
         ELSE 'draft'
       END AS state
FROM rules.version v
LEFT JOIN rules.head h
  ON h.kind = v.kind AND h.name = v.name AND h.digest = v.digest AND h.event = 'activated';

-- Lifecycle order: what an event rests on must be the right kind of event,
-- and a pointer event must replace the current one.
CREATE FUNCTION rules.check_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE head rules.event%ROWTYPE;
BEGIN
    IF NEW.proof_event IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM rules.event WHERE event_id = NEW.proof_event AND event = 'proved') THEN
        RAISE EXCEPTION 'Event % is not a passing proof', NEW.proof_event;
    END IF;
    IF NEW.approval_event IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM rules.event WHERE event_id = NEW.approval_event AND event = 'approved') THEN
        RAISE EXCEPTION 'Event % is not a Rule Activation Approval', NEW.approval_event;
    END IF;
    IF NEW.event IN ('activated', 'retired') THEN
        SELECT * INTO head FROM rules.head WHERE kind = NEW.kind AND name = NEW.name;
        IF head.event_id IS DISTINCT FROM NEW.supersedes THEN
            RAISE EXCEPTION 'Stale pointer for %/%: the current event is %, not %',
                NEW.kind, NEW.name, head.event_id, NEW.supersedes;
        END IF;
        IF NEW.event = 'retired' AND (head.event <> 'activated' OR head.digest <> NEW.digest) THEN
            RAISE EXCEPTION 'Only the active version of %/% can be retired', NEW.kind, NEW.name;
        END IF;
        IF NEW.event = 'activated' AND head.event = 'activated' AND head.digest = NEW.digest THEN
            RAISE EXCEPTION 'Version % is already active', NEW.digest;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER check_event BEFORE INSERT ON rules.event
    FOR EACH ROW EXECUTE FUNCTION rules.check_event();

-- Nothing stored ever changes, whatever the grants say. Row triggers do not
-- fire on TRUNCATE, so a statement trigger covers it.
CREATE FUNCTION rules.refuse_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'The Rules Database is append-only: % on %', TG_OP, TG_TABLE_NAME;
END;
$$;
CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON rules.version
    FOR EACH ROW EXECUTE FUNCTION rules.refuse_change();
CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON rules.event
    FOR EACH ROW EXECUTE FUNCTION rules.refuse_change();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON rules.version
    FOR EACH STATEMENT EXECUTE FUNCTION rules.refuse_change();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON rules.event
    FOR EACH STATEMENT EXECUTE FUNCTION rules.refuse_change();

-- Who may write what. Only an approver writes an approval, and every row
-- names the login that wrote it.
ALTER TABLE rules.version ENABLE ROW LEVEL SECURITY;
ALTER TABLE rules.event   ENABLE ROW LEVEL SECURITY;
CREATE POLICY read_all ON rules.version FOR SELECT USING (true);
CREATE POLICY read_all ON rules.event   FOR SELECT USING (true);
CREATE POLICY agent_saves ON rules.version FOR INSERT TO rules_writer
    WITH CHECK (saved_by = session_user);
CREATE POLICY agent_records ON rules.event FOR INSERT TO rules_writer
    WITH CHECK (event <> 'approved' AND actor = session_user);
CREATE POLICY operator_approves ON rules.event FOR INSERT TO rules_approver
    WITH CHECK (event = 'approved' AND actor = session_user);

GRANT USAGE ON SCHEMA rules TO rules_writer, rules_approver, rules_reader;
GRANT SELECT ON rules.version, rules.event, rules.head, rules.version_state
    TO rules_writer, rules_approver, rules_reader;
GRANT INSERT ON rules.version, rules.event TO rules_writer;
GRANT INSERT ON rules.event TO rules_approver;
RESET ROLE;

-- Logins: one per agent runtime, one per person who may approve.
-- An agent's login must never be a member of rules_approver.
-- CREATE ROLE agent_claude  LOGIN IN ROLE rules_writer;
-- CREATE ROLE operator_paul LOGIN IN ROLE rules_approver, rules_reader;
```

What the body holds:

- **A Source Contract** is stored as the whole contract (spec §7). `source
  save` adds one reserved key, `files`, which maps `custom.py` and each
  fixture path to its SHA-256. So the version digest also pins the code and
  fixtures. This matters because `source run` skips work by `(artifact
  sha256, contract digest)` (`spec.md:831-833`). If a change to `custom.py`
  left the digest unchanged, `source run` would skip artifacts it should
  re-parse. `source export` leaves `files` out of the YAML it writes.
- **A Mastering Policy** is stored exactly as `register_policy` receives it
  (`store.py:185-228`). The one exception is the approval stamps (§7,
  question 3).

What each event's `detail` holds:

- `proved` / `proof_failed`: the proof of spec §16 (`spec.md:783-786`):
  engine version, each metric with its value, limit and `why`, and the
  merge summary. The batch hash lives only in the `batch_hash` column, not
  again in `detail`.
- `approved`: the question the agent asked, and the operator's reason. The
  approver is `actor`, which row-level security forces to be the
  operator's own login. The time is `recorded_at`, and the digest is
  `digest`.
- `activated`: `clean_mdm`, which is what Clean MDM holds after
  registration. For a Source Contract, `register_dataset` returns nothing
  (`store.py:231-238`). So the command reads the reading back with
  `current_reading` (`store.py:352-368`) and records `source_code`,
  `mapping_version` and `registry_version`. For a policy it is the digest
  D′ that `register_policy` returns (`store.py:228`).
- `retired`: `why`.

The `kind` and `name` columns on `event` repeat the version's. They are
foreign-key-checked keys that the per-name index needs, not a second body.

### 4.2 How the tension is resolved

- The body lives in `version` only, one row per digest. `source save` uses
  `INSERT … ON CONFLICT (digest) DO NOTHING`, so saving the same bytes twice
  is a no-op. There is never a second copy.
- State lives in `event` only, and every event is a new row.
- No row is ever updated, and no "current" column exists anywhere. `head`
  and `version_state` are views, so they are computed and cannot drift.

### 4.3 How immutability is enforced

Three independent layers are used, following Clean MDM's own reasoning
("even if future privilege grants drift",
`edgar_warehouse/mdm/migrations/023_clean_mdm.sql:95-106`):

1. **Grants.** The writer and approver roles have `INSERT` and `SELECT`
   only. Neither can `UPDATE`, `DELETE` or `TRUNCATE`. Tested: "permission
   denied".
2. **Triggers.** A `BEFORE UPDATE OR DELETE` row trigger and a `BEFORE
   TRUNCATE` statement trigger refuse every change, including the table
   owner's. Tested. Clean MDM's `immutable_row` does not cover `TRUNCATE`,
   because row triggers never fire for it (PostgreSQL 16, CREATE TRIGGER).
3. **Row-level security.** Only a login in `rules_approver` can write
   `approved`, and every row's `actor` or `saved_by` must equal
   `session_user`. So an agent cannot approve its own version or write
   under a person's name. Tested. This is how the schema enforces
   `CONTEXT.md:175` ("Avoid: … agent self-approval of identity-changing
   rules"). A table owner and a superuser bypass row-level security
   (PostgreSQL 16, §5.8). The owner role therefore has no login.

**What the database cannot check**, and so remains the command's job: JSON
Schema validation, the canonical form, running the proof, and the agent's
statement of whether a change `adds_data` or `binds_or_merges`. The database
records that statement with its actor. It refuses a `binds_or_merges`
activation that has no approval. It cannot tell whether the statement is
true. "Never raw SQL" is therefore partly a convention, backed by giving the
writer login only to the command runner. Clean MDM's alternative is `SECURITY
DEFINER` functions as the only write path (`store.py:146-163`). That would
add five functions that re-check less than the Python command does, so the
triggers and policies above were chosen instead.

### 4.4 How "active" is derived, and how one active per name is enforced

- Every `activated` or `retired` event names in `supersedes` the pointer
  event it replaces. The first activation of a name names `NULL`.
- The partial unique index `event_one_successor` on `(kind, name,
  supersedes) NULLS NOT DISTINCT` lets only one event replace a given one,
  and only one event be first. `NULLS NOT DISTINCT` makes two `NULL`s
  count as equal (PostgreSQL 16, CREATE INDEX).
- So each name's pointer events form one chain, and `head`, the event that
  nothing supersedes, is unique. If `head` is an activation, its digest is
  the active version. If it is a retirement, the name has no active
  version.
- The trigger refuses a stale `supersedes`, which keeps the chain in order.
  It cannot see another session's uncommitted row, so the unique index
  settles races. Tested: two concurrent activations; the second waited for
  the first to commit, then failed on `event_one_successor`.
- **Retirement by replacement is derived.** A version is `retired` when it
  was once activated and is no longer `head`. Spec §4.2 says retirement
  comes from "the activation that replaces it" (`spec.md:86`). The
  `supersedes` link is that record. An explicit `retired` event is needed
  only to withdraw a source with no successor.
- **Rollback** is a new activation of an older proven digest. The schema
  allows it; Clean MDM records it as a new reading (§7, question 5).
- **A later failed proof does not demote a proven version.** A proof is
  pinned to its batch, so a failure on another batch is a record, not a
  change of state. This is a recommendation, not a decided rule.
- **Why no exclusion constraint.** An `EXCLUDE USING gist (name WITH =,
  period WITH &&)` over validity ranges would need each range's end
  updated when a version retires. That breaks append-only. The successor
  index gives the same guarantee without updating anything.

### 4.5 The digest

- The body column is `text` holding the canonical JSON: sorted keys, no
  whitespace, UTF-8 (`store.py:23-34`). The CHECK recomputes
  `sha256(convert_to(body,'UTF8'))`, so the database guarantees that the
  digest belongs to the stored bytes.
- Tested: Python's `canonical()` digest and PostgreSQL's digest matched on
  a body with Hebrew text, an em dash, an escaped quote and a backslash.
- `jsonb` was not used for the body. It "does not preserve white space,
  does not preserve the order of object keys" (PostgreSQL 16, §8.14), so the
  database could not check the digest. It also rejects `\u0000`. Clean MDM
  stores `jsonb` plus a Python digest (`023_clean_mdm.sql:10-13`), and the
  database cannot check those digests. The Rules Database casts with
  `body::jsonb` when it needs a key. At a few hundred versions, the cost is
  negligible.
- `convert_to` is `STABLE`, not `IMMUTABLE` (checked in `pg_proc`).
  PostgreSQL assumes CHECK conditions are immutable, but it does not refuse
  a stable function (PostgreSQL 16, §5.4). Here the only input that could
  change the result is the database encoding, which is fixed at creation.
  So the database must be created with `ENCODING 'UTF8'`.
- The database checks the digest, not canonical form. A body saved with
  unsorted keys would pass under its own digest. Canonicalization is
  `source save`'s job, as it is `register_policy`'s today.

### 4.6 Commands to rows

| Command | Writes | Reads |
|---|---|---|
| `source save <file\|folder>` | 1 `version` row per contract, with `ON CONFLICT (digest) DO NOTHING`. Initialization is `save` over a folder: N rows | nothing |
| `source prove <name\|file>` | 1 `event`: `proved` or `proof_failed`, with `batch_hash` and the proof in `detail`. A failed run stays as a record, and the version stays draft | the `version` body |
| approve (by the operator, through their own login) | 1 `event`: `approved`, naming the `proof_event` it rests on | `version_state`, and the proof |
| activate | 1. Take `head` for the name. 2. Register into Clean MDM in Clean MDM's own transaction: `register_dataset(conn, source_code, registry_version, dataset.contract)` or `register_policy(conn, D′)`. This needs Clean MDM's governance-owner login, because the runtime role cannot insert (`store.py:186`), and for datasets the acquisition registry version (`store.py:274-288`). 3. Read back what Clean MDM now holds (`current_reading` for a dataset; `register_dataset` returns nothing). 4. Insert 1 `event`: `activated`, with `supersedes = head.event_id`, `proof_event`, `approval_event` when `binds_or_merges`, and `detail.clean_mdm`. **The two commits cannot be one transaction** (§5). Clean MDM goes first, because both register calls are idempotent for an unchanged input (`store.py:299-302`, `:222-227`). **A rerun must not call `register_dataset` blindly.** If the acquisition registry version moved between attempts, the old version fails the authority check (`store.py:283-288`), and the new one is refused as "a registry version bump is not a new reading" (`:303-306`). So on rerun the command first compares the current reading's body, without `registry_evidence`, to the intended body. If they match, it skips registration and records the event. **Caveat:** a version that changes only `read`, `silver` or `custom.py` leaves the Dataset Contract unchanged. `register_dataset` then returns without minting a new reading (`store.py:299-302`) (§7, question 2) | `version`, `head`, the proof and approval events |
| retire (withdraw a source) | 1 `event`: `retired`, superseding `head` | `head` |
| `source export <name> <version>` | nothing | 1 `version` row; `body::jsonb` written out as YAML, without `files`. Comments never entered the digest (`spec.md:156-157`) |
| status | nothing | `version_state`, `head` |

### 4.7 What was tested

All on PostgreSQL 16.15 (`postgres:16-alpine`), in the throwaway container
`rules-db-sc11-research`, which was removed afterwards. The tests connected
as real logins: `agent_claude` in `rules_writer`, and `operator_paul` in
`rules_approver`. Cases marked * ran on the first draft of the DDL, whose
pointer logic and grants are unchanged in the final version.

| Case | Result |
|---|---|
| save the same body twice | the second insert is a no-op (`INSERT 0 0`) |
| digest does not match the body | CHECK refused |
| name differs from the body's `source` | CHECK refused |
| `saved_by` names someone else | row-level security refused |
| a proof without a batch hash | CHECK refused |
| the agent writes an approval | row-level security refused |
| the agent sets `actor` to the operator | row-level security refused |
| an activation resting on the failed run | trigger refused: "not a passing proof" |
| an activation resting on another version's proof | composite foreign key refused |
| `binds_or_merges` without an approval | CHECK refused |
| the operator approves | accepted; `actor = operator_paul` |
| the operator writes a proof | row-level security refused |
| an approval resting on the failed run | trigger refused |
| activate v1, then v2 superseding it | v1 `retired`, v2 `active`, both derived |
| a second "first" activation* | trigger refused: stale pointer |
| retire a version that is not active* | trigger refused |
| retire the active version* | the name has no active version |
| UPDATE, DELETE or TRUNCATE by the writer | permission denied |
| UPDATE or TRUNCATE by the table owner | trigger refused |
| an INSERT by the reader* | permission denied |
| two concurrent activations | the second waited, then failed on `event_one_successor` |
| Python digest vs `sha256(convert_to(body,'UTF8'))` | equal |
| shape 1's foreign key to a partial unique index | refused, as the docs say |
| shape 3 | 19 tables created |

## 5. Separate database or separate schema

| Property | Separate database | Schema in `mdm_v2`'s database |
|---|---|---|
| Can production reach it? | Only with a `CONNECT` grant, which is checked at connection startup (PostgreSQL 16, §5.7). Production is not given one | Any role given `USAGE` can. "Schemas are not rigidly separated" (PostgreSQL 16, §5.9) |
| Cross-database queries | "It is not possible to access more than one database per connection" (PostgreSQL 16, §23.1). Only possible through `dblink` or `postgres_fdw`. Tested: `cross-database references are not implemented` | a plain join |
| Activation as one transaction | not possible. Two-phase commit "is not intended for use in applications" (PostgreSQL 16, PREPARE TRANSACTION). So: Clean MDM first, idempotently; rerun on failure | possible |
| Backup, restore, local reset | its own dump, its own `DROP DATABASE` | tied to the production MDM database's backups |
| Roles | cluster-wide either way (PostgreSQL 16, §22.1) | the same |
| Default privileges | a new database grants `CONNECT` and `TEMPORARY` to `PUBLIC`, so the DDL revokes them. Tested: `PUBLIC` could connect to a new database until revoked | no default privileges on a schema |
| Proving Runs | need their own throwaway database either way, because Clean MDM's migration creates the fixed schema name `mdm_v2` (`023_clean_mdm.sql:3`) | the same |

**Recommendation: a separate database** named `rules`, with one schema
`rules` inside it. It matches the fixed "its own Postgres". Production is
not given a connection, so "production never reads the Rules Database"
becomes a connection-level fact rather than only a naming rule. It also
moves as a unit when "local first" becomes hosted. The one thing given up is
an atomic activation. Idempotent registration makes that safe, and a
`source status` comparison of `head` with Clean MDM's current reading would
show any gap.

## 6. What Clean MDM can then keep less of

This section depends on §7, question 1. If production were to read the whole
active Source Contract from `mdm_v2`, Clean MDM would keep more, not less.
The recommended answer to question 1 keeps it lean. Everything here is a
proposal to Codex, who owns these files.

**What exists today:**

- `mdm_v2.policy (digest, body)` is append-only, and batches reference it
  (`023_clean_mdm.sql:10-13`, `:24`, `:102`). **It is already minimal**: a
  digest-keyed, immutable copy of each registered policy. Keep it.
- `mdm_v2.dataset (source_code, registry_version, body)` is append-only. It
  holds the first contract ever registered and never changes
  (`023_clean_mdm.sql:15-19`; `store.py:319-331`).
- `mdm_v2.dataset_mapping (source_code, mapping_version, body,
  registry_version)` holds every reading. The current reading is the
  highest one (`031_clean_mdm_mapping_version.sql:35-48`;
  `store.py:352-368`).
- **The body is in two places.** Reading 1 is written to both tables
  (`store.py:319-331`), and 031 copied every existing body into reading 1
  (`031_clean_mdm_mapping_version.sql:50-52`).
- **Five readers still read the frozen first body:**
  1. the publication-family check in `commit_batch_core`
     (`029_clean_mdm_family_checkpoint.sql:23-27`; restated in
     `041_clean_mdm_company_one_place.sql:117-121` on
     `claude/company-mastering-17-company-one-place`);
  2. the registry-authority check in `commit_batch_core`
     (`023_clean_mdm.sql:154-159`; restated in `041…sql:147-152`);
  3. the deferred-review blocking check in `commit_batch_evidence`
     (`030_clean_mdm_evidence_disposition.sql:26`, `:35`, `:55-59`);
  4. `edgar_warehouse/mdm/clean/merge.py:616-622`;
  5. `edgar_warehouse/mdm/clean/source_publications.py:154-158`.

  So a corrected mapping that adds a publication family or a nonblocking
  deferred reason registers, but has no effect on these checks.
- Four tables have foreign keys to `dataset(source_code)`: `assertion`
  (`023:43`), `deferred_record` (`027:4`), `dataset_mapping` (`031:40`) and
  `stage_record` (`038:25`).

**Proposed minimal Clean MDM side:**

- `mdm_v2.policy`: unchanged.
- `mdm_v2.dataset_mapping`: unchanged. It is the immutable copy of every
  activated reading. The Rules Database's `activated` event records
  `(source_code, mapping_version)`, so the link needs no new column in
  `mdm_v2`.
- `mdm_v2.dataset`: shrinks to the **list of source codes**. The four
  foreign keys stay as they are, at no cost.
- Clean MDM needs no drafts, proofs, approvals or lifecycle states. It
  holds none today, and none should be added.

**Proposed steps for Codex, in order:**

1. Move the five readers to `dataset_mapping`:
   - The registry-authority check reads the reading the assertion names.
     That is the same row 031's schema check already reads
     (`031…sql:68-73`), and it carries its own `registry_version`
     (`031…sql:43`).
   - The publication-family check asks whether any reading of that family
     declares the publication family.
   - `source_publications.py` uses `current_reading` (`store.py:352-368`).
   - The deferred-blocking check and `merge.py` **need a rule first**:
     which reading's `nonblocking_deferred_reasons` apply? Deferred
     records carry no reading (`032_clean_mdm_deferred_reading.sql:9-15`).
     The simplest rule is the current reading at commit time. The
     stricter rule is the reading the run pinned
     (`native_consumption.py:149-160`).
2. Make the first registration insert only the source code
   (`store.py:319-331`).
3. Drop `dataset.body` and `dataset.registry_version`. Nothing is lost:
   `dataset_mapping` reading 1 holds the same bytes. Readers must move
   first, because `src mdm_v2.dataset%ROWTYPE` is declared in the capability
   functions (`027:18`, `030:5`, `041:103`).

**Cost:** one migration that restates `commit_batch_core` and
`commit_batch_evidence` in full. 029, 031, 032, 038 and 039 edited them as
text, which is why 041 already had to restate the core
(`041…sql:26-28`). Also three Python edits, and their tests.

**Gain:** each contract body is in one place, with no frozen first reading.

## 7. Open questions for the operator

1. **Where does production `source run` get `read`, `silver` and
   `custom.py`, and how does it learn which policy is active?** No document
   says. Only `dataset.contract` reaches Clean MDM. Production never reads
   the Rules Database. A policy's digest reaches a run through its manifest
   (`edgar_warehouse/mdm/clean/cli.py:327`, `:348`), not through any
   "active" record in `mdm_v2`.
   *Recommendation:* at activation, add one key to the Dataset Contract body
   it registers: the Source Contract digest. That needs no DDL; the body is
   stored as given, and a changed key becomes a new reading. `source run`
   then reads that digest from the current reading and loads the exported
   folder (`contract.yaml`, `custom.py`) named by it. It refuses the folder
   if the digests differ. That is spec §4.1's proposed rule
   (`spec.md:66-68`). Policies keep being pinned by the run manifest.
   *Rejected alternative:* storing whole Source Contracts in `mdm_v2`. It
   would tie Clean MDM to parsing, against "sources fully decoupled".
   *Dependency:* the stamp works today only because `register_dataset`
   stores any body. If Codex adds validation at registration (handover item
   X1) that refuses unknown keys, the stamp must be one of the allowed keys.
2. **A change to parsing alone can fail a production batch.** Say a version
   changes only `read`, `silver` or `custom.py`:
   - `source run`'s skip key changes, so old artifacts are parsed again
     (`spec.md:831-833`).
   - The Dataset Contract is identical, so `register_dataset` keeps the
     same reading (`store.py:299-302`).
   - A record that now parses to a different value gets a new
     `assertion_id` under the same `(source_code, record_key,
     publication_key, mapping_version)`. The assertion insert tolerates a
     duplicate `assertion_id` only (`041…sql` core; `031…sql:82-87`), so
     the 031 unique key (`031…sql:31-32`) fails the whole batch.

   Tested on a replica of that key: unique violation. This ties to spec §25
   item 3, Change and replay (`spec.md:1041-1042`).
   *Recommendation:* the fix in question 1. The stamped digest makes every
   activated Source Contract version a new reading, so re-read records sit
   beside the old ones instead of colliding. The cost is new assertion rows
   for every re-read record.
   *Alternative:* the author bumps `adapter.version`. It enters every
   assertion's provenance (`adapters.py:308-319`). This relies on a person
   remembering.
3. **The digest a person approves (D) differs from the one Clean MDM
   registers (D′).** `check_policy` needs the approval stamped inside the
   body (`activation.py:278-279`, `:438-443`). A related difference is
   grain: the Rules Database approves a whole version, and Clean MDM reads
   a stamp on each rule.
   *Recommendation:* the Rules Database approves D. Activation builds D′
   from D and the approval event alone, as a pure function, and records
   both digests in `detail.clean_mdm`. A test can recompute D′.
   Separately, propose to Codex (not blocking) that `register_policy`
   accept the approval beside the body, so that D = D′.
4. **Does every Mastering Policy version need a Rule Activation Approval,
   or only one that can bind or merge?** §4.3 says only binding or merging
   versions (`spec.md:92-99`). §13.2a calls any policy change "a
   deliberate, separately approved step, because ranking a source changes
   other sources' winners" (`spec.md:587-590`).
   *Recommendation:* every policy version needs one. If you agree, the
   schema enforces it with one CHECK on activations only: `CHECK (event <>
   'activated' OR kind <> 'mastering_policy' OR approval_event IS NOT
   NULL)`. (Without the `event` term, it would forbid a policy's proofs and
   approvals as well.)
5. **May a retired version become active again (rollback)?** The schema
   allows it. Clean MDM would record it as a new reading, because its body
   differs from the current one.
   *Recommendation:* allow it, under the same approval rule as any other
   activation. Rollback is then one command, with no special path.

## 8. Sources

Repository (branch `claude/source-contract-11-rules-database-schema`, on
`origin/main` at `082d9461`, unless noted):

- `docs/specs/source-contract/spec.md` §4 (`:56-128`), §7, §13.2a
  (`:579-597`), §16 (`:749-790`), §18 (`:826-842`), §23 (`:988-1005`), §25
  (`:1034-1054`)
- `.scratch/source-contract/issues/06-decide-how-a-source-contract-is-registered-and-run.md`,
  `.scratch/source-contract/map.md`, `CONTEXT.md:149-179`
- `.scratch/handover/2026-09-21-claude-to-codex-source-contract.md` (item 4)
- `edgar_warehouse/mdm/clean/store.py` (`canonical`/`digest` `:23-34`;
  `migrate` grants `:146-177`; `register_policy` `:185-228`;
  `register_dataset` `:231-331`; `current_reading` `:352-368`;
  `reading_at` `:371-390`; `protected_change` `:343-349`, `:393-413`)
- `edgar_warehouse/mdm/clean/activation.py:255-279`, `:425-443`;
  `evidence.py:97-104`; `adapters.py:308-319`; `cli.py:142-147`, `:327`,
  `:348`; `merge.py:616-637`; `source_publications.py:147-170`;
  `native_consumption.py:149-160`
- `edgar_warehouse/mdm/migrations/014_source_registry.sql:49-75` (an existing
  versioned registry that UPDATEs a status column, with a partial unique
  index for "single active"), `023`, `027`, `029`, `030`, `031`, `032`,
  `037:4-56`, `038:24-46`
- `edgar_warehouse/mdm/migrations/041_clean_mdm_company_one_place.sql`, in
  worktree `claude-cm-17`, branch
  `claude/company-mastering-17-company-one-place` at `efd37f21`
- `.scratch/source-contract/prototype/` (README, `policies/mastering-policy.yaml`,
  `sources/gleif/contract.yaml`, `rules_db/*/…proof.json`), read only
- `origin/claude/company-mastering-05-proving-run:.scratch/company-mastering/research/05-candidate-policy.json`

PostgreSQL 16 documentation:

- Databases overview, §23.1: https://www.postgresql.org/docs/16/manage-ag-overview.html
- Schemas, §5.9: https://www.postgresql.org/docs/16/ddl-schemas.html
- Privileges, §5.7: https://www.postgresql.org/docs/16/ddl-priv.html
- Row security policies, §5.8: https://www.postgresql.org/docs/16/ddl-rowsecurity.html
- Database roles, §22.1: https://www.postgresql.org/docs/16/database-roles.html
- Constraints (foreign keys, CHECK, EXCLUDE), §5.4: https://www.postgresql.org/docs/16/ddl-constraints.html
- Partial unique indexes, §11.8: https://www.postgresql.org/docs/16/indexes-partial.html
- CREATE INDEX (`NULLS NOT DISTINCT`): https://www.postgresql.org/docs/16/sql-createindex.html
- Generated columns, §5.3: https://www.postgresql.org/docs/16/ddl-generated-columns.html
- CREATE TRIGGER (TRUNCATE is statement-level only): https://www.postgresql.org/docs/16/sql-createtrigger.html
- JSON types and GIN operator classes, §8.14: https://www.postgresql.org/docs/16/datatype-json.html
- PREPARE TRANSACTION: https://www.postgresql.org/docs/16/sql-prepare-transaction.html

Versioned registries used as comparisons:

- **Confluent Schema Registry** keeps each schema body once under a global
  ID. "Two registrations of an identical schema definition share the same
  schema ID." A subject holds an ordered sequence of versions, and
  "registering the same schema under a subject doesn't create a new
  version". This matches `version` keyed by digest, with `ON CONFLICT DO
  NOTHING`. Source: https://docs.confluent.io/platform/current/schema-registry/fundamentals/index.html.
  A soft delete keeps the schema ID resolvable
  (https://docs.confluent.io/platform/current/schema-registry/schema-deletion-guidelines.html).
  Retirement here likewise never removes a body.
- **MLflow Model Registry** keeps versions immutable. It moves "a mutable,
  named reference to a particular version" (an alias) "by reassigning the
  alias to a different model version". That is `head`, except that here
  the reassignment is an appended event, not an update. Source:
  https://mlflow.org/docs/latest/ml/model-registry/.
