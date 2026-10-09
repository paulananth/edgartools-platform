# Profiling report: None

Profiled 2026-10-09T16:44:30-04:00 by data-profiling 1. Scan: **full**; 12.1 s. Approval: **draft**.

## Parts

| Part | Rows | Class | Confidence | Record key | Store (advice) |
|---|---|---|---|---|---|
| dtc_1_1 | 918 | unknown | 0.0 | record_id (designed: surrogate) | bronze_only |
| dtc_2_1 | 990 | unknown | 0.0 | record_id (designed: surrogate) | bronze_only |
| dtc_3_1 | 49 | unknown | 0.0 | record_id (designed: surrogate) | bronze_only |
| dtc_4_1 | 58 | unknown | 0.0 | record_id (designed: surrogate) | bronze_only |
| dtc_5_1 | 62 | unknown | 0.0 | record_id (designed: surrogate) | bronze_only |
| ficc_gov_1_1 | 6 | reference | 0.857 | Member ID | rdm |
| ficc_gov_2_1 | 308 | unknown | 0.0 | record_id (designed: surrogate) | bronze_only |
| ficc_mbs_1_1 | 139 | unknown | 0.0 | record_id (designed: surrogate) | bronze_only |
| nscc_1_1 | 5365 | unknown | 0.0 | record_id (designed: surrogate) | bronze_only |
| nscc_1_2 | 1 | unknown | 0.0 | record_id (designed: surrogate) | bronze_only |
| nscc_2_1 | 2028 | master | 0.667 | EXECUTING BROKER MPID | mdm |
| nscc_2_2 | 1398 | master | 0.833 | EXECUTING BROKER MPID, CLEARING BROKER | mdm |
| nscc_2_3 | 1367 | master | 0.667 | EXECUTING BROKER MPID | mdm |
| nscc_2_4 | 1181 | master | 0.667 | EXECUTING BROKER MPID | mdm |

## Why each class

- **dtc_1_1** is unknown: points at few parts; has name-like text; has attributes besides codes and dates; at most 10000 rows; points at no other part, or only at a smaller list as its coarser level (required); nothing points at it; few attributes besides codes and dates; points at as many parts as point at it; at least as large as the parts it points at; nothing points at it; points at no other part. Failed: has a unique key (required); other parts point at it; smaller than the parts pointing at it; has a unique key (required); other parts point at it; no name-like text besides labels; codes with label columns; only codes, labels and dates; key made of links to other parts (required); points at two or more parts; has a unique key (required); points at other parts; has an event time or measures; no name-like text; columns describe data (files, hashes, counts) (required).
- **dtc_2_1** is unknown: points at few parts; has name-like text; has attributes besides codes and dates; at most 10000 rows; points at no other part, or only at a smaller list as its coarser level (required); nothing points at it; few attributes besides codes and dates; points at as many parts as point at it; at least as large as the parts it points at; nothing points at it; points at no other part. Failed: has a unique key (required); other parts point at it; smaller than the parts pointing at it; has a unique key (required); other parts point at it; no name-like text besides labels; codes with label columns; only codes, labels and dates; key made of links to other parts (required); points at two or more parts; has a unique key (required); points at other parts; has an event time or measures; no name-like text; columns describe data (files, hashes, counts) (required).
- **dtc_3_1** is unknown: points at few parts; at most 10000 rows; points at no other part, or only at a smaller list as its coarser level (required); no name-like text besides labels; codes with label columns; only codes, labels and dates; nothing points at it; few attributes besides codes and dates; points at as many parts as point at it; no name-like text; at least as large as the parts it points at; nothing points at it; points at no other part. Failed: has a unique key (required); other parts point at it; has name-like text; smaller than the parts pointing at it; has attributes besides codes and dates; has a unique key (required); other parts point at it; key made of links to other parts (required); points at two or more parts; has a unique key (required); points at other parts; has an event time or measures; columns describe data (files, hashes, counts) (required).
- **dtc_4_1** is unknown: points at few parts; has name-like text; has attributes besides codes and dates; at most 10000 rows; points at no other part, or only at a smaller list as its coarser level (required); nothing points at it; few attributes besides codes and dates; points at as many parts as point at it; at least as large as the parts it points at; nothing points at it; points at no other part. Failed: has a unique key (required); other parts point at it; smaller than the parts pointing at it; has a unique key (required); other parts point at it; no name-like text besides labels; codes with label columns; only codes, labels and dates; key made of links to other parts (required); points at two or more parts; has a unique key (required); points at other parts; has an event time or measures; no name-like text; columns describe data (files, hashes, counts) (required).
- **dtc_5_1** is unknown: points at few parts; has name-like text; has attributes besides codes and dates; at most 10000 rows; points at no other part, or only at a smaller list as its coarser level (required); nothing points at it; few attributes besides codes and dates; points at as many parts as point at it; at least as large as the parts it points at; nothing points at it; points at no other part. Failed: has a unique key (required); other parts point at it; smaller than the parts pointing at it; has a unique key (required); other parts point at it; no name-like text besides labels; codes with label columns; only codes, labels and dates; key made of links to other parts (required); points at two or more parts; has a unique key (required); points at other parts; has an event time or measures; no name-like text; columns describe data (files, hashes, counts) (required).
- **ficc_gov_1_1** is reference: has a unique key (required); at most 10000 rows; points at no other part, or only at a smaller list as its coarser level (required); no name-like text besides labels; codes with label columns; only codes, labels and dates. Failed: other parts point at it.
- **ficc_gov_2_1** is unknown: points at few parts; has name-like text; has attributes besides codes and dates; at most 10000 rows; points at no other part, or only at a smaller list as its coarser level (required); nothing points at it; few attributes besides codes and dates; points at as many parts as point at it; at least as large as the parts it points at; nothing points at it; points at no other part. Failed: has a unique key (required); other parts point at it; smaller than the parts pointing at it; has a unique key (required); other parts point at it; no name-like text besides labels; codes with label columns; only codes, labels and dates; key made of links to other parts (required); points at two or more parts; has a unique key (required); points at other parts; has an event time or measures; no name-like text; columns describe data (files, hashes, counts) (required).
- **ficc_mbs_1_1** is unknown: points at few parts; has name-like text; has attributes besides codes and dates; at most 10000 rows; points at no other part, or only at a smaller list as its coarser level (required); only codes, labels and dates; nothing points at it; few attributes besides codes and dates; points at as many parts as point at it; at least as large as the parts it points at; nothing points at it; points at no other part. Failed: has a unique key (required); other parts point at it; smaller than the parts pointing at it; has a unique key (required); other parts point at it; no name-like text besides labels; codes with label columns; key made of links to other parts (required); points at two or more parts; has a unique key (required); points at other parts; has an event time or measures; no name-like text; columns describe data (files, hashes, counts) (required).
- **nscc_1_1** is unknown: points at few parts; has name-like text; has attributes besides codes and dates; at most 10000 rows; points at no other part, or only at a smaller list as its coarser level (required); nothing points at it; points at as many parts as point at it; at least as large as the parts it points at; nothing points at it; points at no other part. Failed: has a unique key (required); other parts point at it; smaller than the parts pointing at it; has a unique key (required); other parts point at it; no name-like text besides labels; codes with label columns; only codes, labels and dates; key made of links to other parts (required); points at two or more parts; few attributes besides codes and dates; has a unique key (required); points at other parts; has an event time or measures; no name-like text; columns describe data (files, hashes, counts) (required).
- **nscc_1_2** is unknown: points at few parts; at most 10000 rows; points at no other part, or only at a smaller list as its coarser level (required); no name-like text besides labels; only codes, labels and dates; nothing points at it; few attributes besides codes and dates; points at as many parts as point at it; no name-like text; at least as large as the parts it points at; nothing points at it; points at no other part. Failed: has a unique key (required); other parts point at it; has name-like text; smaller than the parts pointing at it; has attributes besides codes and dates; has a unique key (required); other parts point at it; codes with label columns; key made of links to other parts (required); points at two or more parts; has a unique key (required); points at other parts; has an event time or measures; columns describe data (files, hashes, counts) (required).
- **nscc_2_1** is master: has a unique key (required); points at few parts; has name-like text; has attributes besides codes and dates. Failed: other parts point at it; smaller than the parts pointing at it.
- **nscc_2_2** is master: has a unique key (required); other parts point at it; points at few parts; has name-like text; has attributes besides codes and dates. Failed: smaller than the parts pointing at it.
- **nscc_2_3** is master: has a unique key (required); points at few parts; has name-like text; has attributes besides codes and dates. Failed: other parts point at it; smaller than the parts pointing at it.
- **nscc_2_4** is master: has a unique key (required); points at few parts; has name-like text; has attributes besides codes and dates. Failed: other parts point at it; smaller than the parts pointing at it.

## Relationships

| From | To | Inclusion | Cardinality | Onboard | Why |
|---|---|---|---|---|---|
| nscc_2_4.EXECUTING BROKER MPID, CLEARING BROKER | nscc_2_2.EXECUTING BROKER MPID, CLEARING BROKER | 0.988146 | 1:1 | separate | a master part pointing at a master part: onboarded after it |

## Hierarchies

None found.

## Identifiers, sensitive columns and time

- **dtc_1_1**: identifiers: No (cross_reference)
- **dtc_4_1**: identifiers: Pledgee Number (cross_reference)
- **dtc_5_1**: identifiers: Number (cross_reference)
- **ficc_gov_1_1**: identifiers: Member ID (record_key)
- **nscc_1_1**: identifiers: gustno (cross_reference), clearing no (cross_reference), exchg (none)
- **nscc_2_1**: identifiers: EXECUTING BROKER MPID (record_key), CLEARING BROKER (none)
- **nscc_2_2**: identifiers: EXECUTING BROKER MPID (record_key), CLEARING BROKER (record_key)
- **nscc_2_3**: identifiers: EXECUTING BROKER MPID (record_key), CLEARING BROKER (none)
- **nscc_2_4**: identifiers: EXECUTING BROKER MPID (record_key), CLEARING BROKER (none)

## Data quality to hand to data-quality

- dtc_1_1: no_natural_key: no column or combination is unique
- dtc_2_1: no_natural_key: no column or combination is unique
- dtc_3_1: code_list: 47 codes in this delivery; a new code is flagged until the code set has it
- dtc_3_1: no_natural_key: no column or combination is unique
- dtc_4_1: no_natural_key: no column or combination is unique
- dtc_5_1: no_natural_key: no column or combination is unique
- ficc_gov_2_1: code_list: 8 codes in this delivery; a new code is flagged until the code set has it
- ficc_gov_2_1: no_natural_key: no column or combination is unique
- ficc_mbs_1_1: code_list: 3 codes in this delivery; a new code is flagged until the code set has it
- ficc_mbs_1_1: no_natural_key: no column or combination is unique
- nscc_1_1: placeholder: a stand-in for no value, which must not match or merge
- nscc_1_1: no_natural_key: no column or combination is unique
- nscc_1_2: no_natural_key: no column or combination is unique

## Questions for the operator (one at a time)

1. dtc_1_1 has no unique column: use the designed key? Recommendation: a durable id given when a record first appears and kept in a key map, so it never changes; the operator chooses which columns identify a record (candidates: none)
2. Which class is dtc_1_1? Its tests did not decide. Recommendation: keep it raw (bronze only) until decided
3. dtc_2_1 has no unique column: use the designed key? Recommendation: a durable id given when a record first appears and kept in a key map, so it never changes; the operator chooses which columns identify a record (candidates: none)
4. Which class is dtc_2_1? Its tests did not decide. Recommendation: keep it raw (bronze only) until decided
5. dtc_3_1 has no unique column: use the designed key? Recommendation: a durable id given when a record first appears and kept in a key map, so it never changes; the operator chooses which columns identify a record (candidates: none)
6. Which class is dtc_3_1? Its tests did not decide. Recommendation: keep it raw (bronze only) until decided
7. dtc_4_1 has no unique column: use the designed key? Recommendation: a durable id given when a record first appears and kept in a key map, so it never changes; the operator chooses which columns identify a record (candidates: none)
8. Which class is dtc_4_1? Its tests did not decide. Recommendation: keep it raw (bronze only) until decided
9. dtc_5_1 has no unique column: use the designed key? Recommendation: a durable id given when a record first appears and kept in a key map, so it never changes; the operator chooses which columns identify a record (candidates: none)
10. Which class is dtc_5_1? Its tests did not decide. Recommendation: keep it raw (bronze only) until decided
11. ficc_gov_2_1 has no unique column: use the designed key? Recommendation: a durable id given when a record first appears and kept in a key map, so it never changes; the operator chooses which columns identify a record (candidates: none)
12. Which class is ficc_gov_2_1? Its tests did not decide. Recommendation: keep it raw (bronze only) until decided
13. ficc_mbs_1_1 has no unique column: use the designed key? Recommendation: a durable id given when a record first appears and kept in a key map, so it never changes; the operator chooses which columns identify a record (candidates: none)
14. Which class is ficc_mbs_1_1? Its tests did not decide. Recommendation: keep it raw (bronze only) until decided
15. nscc_1_1 has no unique column: use the designed key? Recommendation: a durable id given when a record first appears and kept in a key map, so it never changes; the operator chooses which columns identify a record (candidates: gustno, services, clearing no, exchg)
16. Which class is nscc_1_1? Its tests did not decide. Recommendation: keep it raw (bronze only) until decided
17. nscc_1_2 has no unique column: use the designed key? Recommendation: a durable id given when a record first appears, kept in a key map looked up by sha256(part, 0x1F, normalized column_1); a rename or variant is kept as an alias of the same id, so the key never changes (operator, 2026-10-05: same record: durable key). name_norm@1: NFKC, case fold, NFKC, whitespace runs to one space, trim (Unicode 15.0.0)
18. Which class is nscc_1_2? Its tests did not decide. Recommendation: keep it raw (bronze only) until decided
19. Is nscc_2_1 a new master kind named 'nscc_2_1'? Recommendation: yes: has a unique key (required); points at few parts; has name-like text; has attributes besides codes and dates
20. Is nscc_2_2 a new master kind named 'nscc_2_2'? Recommendation: yes: has a unique key (required); other parts point at it; points at few parts; has name-like text; has attributes besides codes and dates
21. Is nscc_2_3 a new master kind named 'nscc_2_3'? Recommendation: yes: has a unique key (required); points at few parts; has name-like text; has attributes besides codes and dates
22. Is nscc_2_4 a new master kind named 'nscc_2_4'? Recommendation: yes: has a unique key (required); points at few parts; has name-like text; has attributes besides codes and dates

Samples of personal columns are masked to their shape. Store suggestions are advice only.
