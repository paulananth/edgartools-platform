# Ticket 09 — the task each trial agent was given

The full sandbox instructions were the same in every round. They covered:
- what is in the sandbox: `SPEC.md`, the GLEIF example, `./source`,
  `families.local.yaml`, the data, the policy, and `engine/` readable only for
  `contract.schema.json` and `source_contract.py`;
- the three rules: read and write only inside the sandbox; no questions, so
  log each one instead; edit only the new source folder and `TRIAL-LOG.md`;
- the log format.

The **task** part differed by source. Given in full here, because it carried
more than "only the spec and one example". Those hints matter when reading
the results.

## Rounds 1 and 2 — `sec.company_profile`

> Artifact Family: `sec.submissions_company` — SEC company profile documents, one JSON document per company, as in `data/sec-company-batch/*.json`. Create `sources/sec-company/` with a Source Contract `contract.yaml` whose `source` is `sec.company_profile`. It should:
> - read one silver row per document with the company's main profile fields (identifier, name, entity type, industry code, state of incorporation, fiscal year end, tickers and exchanges, business address city/state, former names) — choose sensible columns and types;
> - map into MDM (the `dataset` section) as a Company keyed by the SEC CIK, **taking the identity kind from the document's entity type so that only operating companies become Companies**;
> - carry Named Cases with fixtures copied from `data/sec-company-batch/` into the source folder, including at least one trap case you find in the real data (e.g. a missing or list-shaped field);
> - declare sensible data checks and a Batch Gate over the whole family;
> - a merge case is optional (it needs Docker).
>
> Reach `version proven` with `./source prove sources/sec-company --gate`, then generate `MAPPING.md`.

**Hints beyond the spec:**
- The list of fields to read.
- The instruction to take the kind from `entityType`, which the agents
  correctly noted cuts against spec §13.4.
- The suggestion of a trap case ("missing or list-shaped").

Round 2 also **reused round 1's source** after the spec had been fixed for
it. So round 2 measures a familiar source, not generality; only rounds 1 and
3 are different sources.

## Round 3 — `iapd.adv_adviser`

> Artifact Family: `iapd.adv_base_filings` — SEC Form ADV Part 1A monthly bulk extracts from investment advisers: one CSV per month, one row per adviser filing, as in `data/adv-base/*.csv`. **Useful columns include `FilingID`, `DateSubmitted`, `1A` (legal name), `1B1` (business name), `1D` (SEC file number), `1E1` (CRD number), `1F1-City`, `1F1-State`, `1F1-Country` (main office), `1N` (is it a public reporting company, Y/N), `1N-CIK`, and `5F2c` (regulatory assets under management).** Create `sources/adv-adviser/` … whose `source` is `iapd.adv_adviser`. It should:
> - read **one silver row per filing** with the adviser's main fields;
> - map into MDM as a Company identified by its CRD number;
> - carry Named Cases with fixtures taken from the real CSV rows …, including at least one trap case;
> - declare sensible data checks and a Batch Gate over the whole family;
> - a merge case is optional.

**Hints beyond the spec:**
- The column glossary. That is domain knowledge a real author would also
  need, but the spec does not supply it.
- "One silver row per filing", which led straight into the record-key
  question (round 3 Q5).

Also, one gap was fixed **before** this round: the CSV reader's `columns:`
header map. It is not counted in round 3's gaps.
