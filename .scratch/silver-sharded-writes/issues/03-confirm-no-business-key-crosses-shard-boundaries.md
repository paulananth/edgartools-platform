# Confirm PROTECTED_TABLE_REGISTRY's Business-Key Uniqueness Never Crosses Shard Boundaries

Type: research
Status: resolved
Blocked by: none

## Question

`silver_protection.py`'s `merge_candidate_into_canonical` does business-key
same-key conflict detection (`PROTECTED_TABLE_REGISTRY`, lines 81-270 per
this session's earlier reading) against the *whole* canonical file today.
If merges become shard-scoped, a same business key that legitimately lives
in two different shards would silently escape conflict detection — each
shard's merge would only ever compare against its own rows.

`migrate_silver_shards.py`'s routing rules already document three
strategies: CIK-direct columns, accession→issuer-CIK join, and "full
replication for global tables." For every table in
`PROTECTED_TABLE_REGISTRY`, confirm which routing strategy applies and
whether that strategy guarantees a given business key always resolves to
exactly one shard (CIK-direct and accession-join tables should, by
construction — a CIK's rows all belong to one shard) or requires full
replication because the same business key could legitimately appear across
CIK ranges (e.g. any table keyed by something other than CIK, like a
CRD-level or cross-entity relationship key). Flag any table where this
isn't obviously true and needs a design decision, not just confirmation.

## Deliverable

Answer inline in this ticket's resolution comment, as a table: table name →
routing strategy → uniqueness-guarantee verdict (safe / needs full
replication / needs a decision). Cite every claim to a `file:line`
reference.

## Answer

All 31 tables from `PROTECTED_TABLE_REGISTRY`
(`edgar_warehouse/silver_protection.py:81-270`, including `pipeline_run_lease`
which is registered there despite also appearing in
`EXCLUDED_OPERATIONAL_TABLES` — see Note 5) cross-referenced against
`migrate_silver_shards.py`'s three routing lists: `CIK_DIRECT_TABLES`
(`edgar_warehouse/application/commands/migrate_silver_shards.py:38-49`),
`ACCESSION_JOIN_TABLES` (`:55-81`), `GLOBAL_TABLES` (`:97-107`).

| Table | Routing strategy | Business key | Verdict |
|---|---|---|---|
| `sec_company` | CIK-direct (`migrate_silver_shards.py:39`) | `(cik,)` (`silver_protection.py:82-84`) | **Safe** — key is the routing column |
| `sec_company_address` | CIK-direct (`:40`) | `(cik, address_type)` (`silver_protection.py:85-87`) | **Safe** — key includes `cik` |
| `sec_company_former_name` | CIK-direct (`:41`) | `(cik, ordinal)` (`silver_protection.py:88-90`) | **Safe** |
| `sec_company_submission_file` | CIK-direct (`:42`) | `(cik, file_name)` (`silver_protection.py:91-93`) | **Safe** |
| `sec_company_ticker` | CIK-direct (`:43`) | `(cik, ticker, source_name)` (`silver_protection.py:97-101`) | **Safe** |
| `sec_company_filing` | CIK-direct (`:45`) | `(accession_number,)` — no `cik` (`silver_protection.py:94-96`; DDL `silver_store.py:97-115`, PK is `accession_number` alone) | **Needs a decision.** `merge_filings` (`silver_store.py:1599-1666`) is called per CIK-window with whatever `cik` that window's own submissions feed reports for the row — it is not a globally-resolved value. `sec_filing_attachment`'s own comment (`silver_protection.py:200-218`) already proves, against live SEC data, that a single `accession_number` can legitimately be associated with many CIKs (a DEFA14A jointly filed by 18 registrants). Two different CIK-windows landing in two different future shards could each independently write "their own" row for the same `accession_number` — a business-key match that CIK-direct routing does not confine to one shard, and that no per-shard merge would ever see both sides of. |
| `sec_current_filing_feed` | CIK-direct (`:46`) | `(accession_number,)` — no `cik` (`silver_protection.py:102-104`; DDL `silver_store.py:128-143`, PK `accession_number` alone) | **Needs a decision.** Same key shape/risk class as `sec_company_filing` above. Could not confirm any current caller of `merge_current_filing_feed` (`silver_store.py:1836`) in the codebase (`grep -rn "merge_current_filing_feed"` returns only the definition), so the actual write pattern — and therefore whether the multi-registrant risk is live in practice today — is unconfirmed, not just unconfirmed-safe. |
| `sec_raw_object` | CIK-direct (`:47`) | `(raw_object_id,)`, a content sha256 (`silver_protection.py:138-141`; DDL `silver_store.py:409-425`, PK `raw_object_id` alone) | **Needs a decision — highest severity finding.** `silver_protection.py:142-181`'s own comment documents that `cik`/`accession_number` on this table are provenance only, because "identical byte content legitimately recurs across different filings … fetched under different accessions/forms/URLs." CIK-direct routing uses exactly that provenance `cik` value to pick a shard. The same content hash, independently first-fetched by two companies in two different CIK bands, would be written as two "new" rows in two different shards — violating the table's own global `PRIMARY KEY` uniqueness across the sharded system, with no merge step ever comparing the two. `migrate_silver_shards.py`'s one-time migration itself is unaffected (it repartitions an already-deduplicated monolithic file, so Layers 1/2 verification at `:266-331` still pass), but ongoing shard-scoped merges are exposed to this. |
| `sec_ownership_reporting_owner` | Accession-join → `sec_company_filing.cik` (`:57-60`) | `(accession_number, owner_index)` (`silver_protection.py:105-107`) | **Safe, conditional on `sec_company_filing`'s own resolution** (see that row above) — the join resolves the shard via `sec_company_filing`'s issuer `cik`, so this table inherits whatever guarantee (or gap) that table has. |
| `sec_ownership_non_derivative_txn` | Accession-join (`:61-65`) | `(accession_number, owner_index, txn_index)` (`silver_protection.py:108-111`) | **Safe, same conditional dependency** as above |
| `sec_ownership_derivative_txn` | Accession-join (`:66-70`) | `(accession_number, owner_index, txn_index)` (`silver_protection.py:112-115`) | **Safe, same conditional dependency** |
| `sec_filing_attachment` | Accession-join (`:71-75`) | `(accession_number, document_name)` (`silver_protection.py:182-219`) | **Safe, same conditional dependency**. The table's own drift history (document_url differing per querying CIK, `silver_protection.py:200-218`) is already handled as provenance and doesn't affect key routing. |
| `sec_filing_text` | Accession-join (`:76-80`) | `(accession_number, text_version)` (`silver_protection.py:221-223`) | **Safe, same conditional dependency** |
| `sec_adv_filing` | Global — full replication (`:103`) | `(accession_number,)` (`silver_protection.py:116`) | **Safe (full replication, already assigned)** — documented rationale at `migrate_silver_shards.py:85-96`: `cik` is NULL for 58,598/58,599 rows, since ADV filers are CRD-identified, not CIK-identified |
| `sec_adv_office` | Global (`:104`) | `(accession_number, office_index)` (`silver_protection.py:117-119`) | **Safe (full replication, already assigned)** |
| `sec_adv_disclosure_event` | Global (`:105`) | `(accession_number, event_index)` (`silver_protection.py:120-122`) | **Safe (full replication, already assigned)** |
| `sec_adv_private_fund` | Global (`:106`) | `(accession_number, fund_index)` (`silver_protection.py:123-125`) | **Safe (full replication, already assigned)** |
| `sec_adv_firm_roster` | **Not covered anywhere in `migrate_silver_shards.py`** | `(adviser_crd_number, dataset_period)` (`silver_protection.py:126-128`) | **Gap + needs a decision.** No `cik` column exists on this table at all (DDL `silver_store.py:263-278`) — it's keyed purely by CRD number, the same non-CIK identifier space `migrate_silver_shards.py:88-90` already documents for ADV data. Almost certainly belongs in `GLOBAL_TABLES` alongside the other three ADV tables, but that has not been decided/added. |
| `sec_subsidiary_evidence` | **Not covered** | `(accession_number, document_name, row_ordinal)` (`silver_protection.py:129-131`) | **Gap.** Has a `registrant_cik` column (`silver_store.py:280-296`) not in the business key — a plausible accession-join candidate (same shape as `sec_filing_attachment`), but not yet added; inherits the same conditional dependency on `sec_company_filing`'s resolution once it is. |
| `sec_auditor_report_evidence` | **Not covered** | `(accession_number, evidence_fingerprint)` (`silver_protection.py:132-134`) | **Gap**, same shape/reasoning as `sec_subsidiary_evidence` — has `registrant_cik` (`silver_store.py:298-318`) but it's not in the key and the table isn't routed |
| `sec_pcaob_firm_identity` | **Not covered** | `(pcaob_firm_id, snapshot_sha256)` (`silver_protection.py:135-137`) | **Gap + needs a decision.** No `cik`/`accession_number` column exists (DDL `silver_store.py:320-331`) — audit firms audit companies across the entire CIK universe, so this is a cross-entity reference table with no CIK affinity at all. Likely needs full replication (small table, like `sec_adv_firm_roster`), undecided. |
| `sec_financial_fact` | **Not covered** | `(cik, accession_number, concept, fiscal_period, segment, period_end, period_start)` (`silver_protection.py:224-228`; DDL `silver_store.py:574-596`) | **Gap — trivially fixable.** Key already includes `cik` directly, so adding this to `CIK_DIRECT_TABLES` would be safe by construction; it simply hasn't been added. |
| `sec_financial_derived` | **Not covered** | `(cik, accession_number, fiscal_period, period_end)` (`silver_protection.py:229-233`; DDL `silver_store.py:598-649`) | **Gap — trivially fixable**, same reasoning |
| `sec_earnings_release` | **Not covered** | `(cik, accession_number)` (`silver_protection.py:234-236`; DDL `silver_store.py:651-674`) | **Gap — trivially fixable**, same reasoning |
| `sec_accounting_flag` | **Not covered** | `(cik, accession_number)` (`silver_protection.py:237-239`; DDL `silver_store.py:723-748`) | **Gap — trivially fixable**, same reasoning |
| `sec_executive_record` | **Not covered** | `(cik, accession_number, exec_name)` (`silver_protection.py:240-242`; DDL `silver_store.py:750-777`) | **Gap — trivially fixable**, same reasoning |
| `sec_thirteenf_holding` | **Not covered** | `(cik, accession_number, holding_index)` — `cik` is "13F filing manager CIK" (`silver_protection.py:243-247`; DDL `silver_store.py:794-817`) | **Gap — trivially fixable**, same reasoning (key already CIK-scoped by the manager's own CIK) |
| `sec_thirteenf_filing` | **Not covered** | `(accession_number,)` (`silver_protection.py:248-250`; DDL `silver_store.py:819-829`, has a `cik` column that is NOT in the PK) | **Gap.** Same key shape as `sec_company_filing`/`sec_current_filing_feed`, but lower risk in practice: a 13F filing has exactly one filing manager, so (unlike jointly-filed 8-Ks/proxies) there is no known multi-registrant concept for this form type — likely safe once added as CIK-direct, but still unrouted today. |
| `sec_employment_event` | **Not covered** | `(accession_number, event_index)` (`silver_protection.py:251-255`; DDL `silver_store.py:779-792`, has a `cik` column not in the PK) | **Gap.** Same key shape as `sec_company_filing`; would most naturally become an accession-join table, inheriting that table's conditional dependency once both are resolved. |
| `sec_guidance_fact` | **Not covered** | `(cik, metric, fiscal_year, fiscal_quarter, as_of, accession_number, is_non_gaap, source_system)` (`silver_protection.py:256-263`; DDL `silver_store.py:681-709`) | **Gap — trivially fixable.** `cik` is the first PK column; safe by construction once added as CIK-direct. |
| `pipeline_run_lease` | **Not covered** | `(lease_name,)` (`silver_protection.py:267-269`) | **Needs a decision — different in kind from every other gap.** This is a system-wide mutual-exclusion lock ("Run-level lease shared by the Daily Identity Refresh and the Identity Backstop Sweep so only one of the two ever runs at a time", `silver_store.py:387-391`), not CIK-scoped business data. Neither CIK-direct routing (no `cik` column) nor the `GLOBAL_TABLES` full-replication pattern is actually safe for it: 4 independent shard copies of "is this lease held" would each be checked/acquired independently, defeating the mutual-exclusion purpose the table exists for (unlike read-mostly reference data, where 4 identical copies is harmless). Needs a single authoritative home, not a routing rule. |

**Note 5 (aside, not part of the verdict table):** `pipeline_run_lease` is
registered in both `PROTECTED_TABLE_REGISTRY` (`silver_protection.py:267-269`)
and `EXCLUDED_OPERATIONAL_TABLES` (`silver_protection.py:298`). Only the
registry membership matters for `merge_candidate_into_canonical`'s actual
merge loop (`silver_protection.py:733`, `for table_name, policy in
PROTECTED_TABLE_REGISTRY.items()`) — `EXCLUDED_OPERATIONAL_TABLES` is
consulted only for the unclassified-table fail-closed check
(`silver_protection.py:714-725`), not to skip merging. This dual membership
doesn't change the verdict above but is worth knowing before touching either
set.

**Summary:** (per-table detail and citations are in the table above; counts
below total 31, matching the registry). All 31 `PROTECTED_TABLE_REGISTRY`
tables fall into six buckets:

1. **Safe, unconditionally (9 tables), already routed**: 5 CIK-direct tables
   whose business key includes `cik` (`sec_company`, `sec_company_address`,
   `sec_company_former_name`, `sec_company_submission_file`,
   `sec_company_ticker`) + 4 ADV tables already on full replication
   (`sec_adv_filing`, `sec_adv_office`, `sec_adv_disclosure_event`,
   `sec_adv_private_fund`).
2. **Safe, conditionally (5 tables), already routed**: the accession-join
   tables (`sec_ownership_reporting_owner`, `sec_ownership_non_derivative_txn`,
   `sec_ownership_derivative_txn`, `sec_filing_attachment`,
   `sec_filing_text`) — safe only if `sec_company_filing` (bucket 4 below)
   is resolved so its join always lands in one shard.
3. **Gap, but trivially safe to close (8 tables)**: not routed anywhere in
   `migrate_silver_shards.py` today, but their business key already includes
   `cik` (or, for `sec_thirteenf_filing`, has no realistic multi-registrant
   concept), so adding a routing entry is safe by construction:
   `sec_financial_fact`, `sec_financial_derived`, `sec_earnings_release`,
   `sec_accounting_flag`, `sec_executive_record`, `sec_thirteenf_holding`,
   `sec_guidance_fact`, `sec_thirteenf_filing`.
4. **Needs a decision — routed today but the routing itself is unsafe (3
   tables)**: `sec_company_filing`, `sec_current_filing_feed` (business key
   excludes `cik`; multi-registrant accessions are empirically confirmed
   elsewhere in this codebase), and `sec_raw_object` (content-hash key,
   `cik` is documented provenance, not identity — highest severity).
5. **Gap + needs a decision — natural accession-join candidates carrying the
   same multi-registrant risk as bucket 4 (3 tables)**:
   `sec_subsidiary_evidence`, `sec_auditor_report_evidence`,
   `sec_employment_event` — each has a `cik`/`registrant_cik` column outside
   its business key, unrouted today.
6. **Gap + needs a decision — no CIK affinity at all (3 tables)**:
   `sec_adv_firm_roster`, `sec_pcaob_firm_identity` (both CRD/firm-keyed,
   likely global-replication candidates) and `pipeline_run_lease` (a
   mutual-exclusion lock — neither CIK-direct nor full-replication is
   actually safe for it; see its table row above).
