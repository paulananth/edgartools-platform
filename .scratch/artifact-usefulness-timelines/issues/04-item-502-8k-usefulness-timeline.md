# Item 5.02 8-K usefulness timeline

Type: research
Status: resolved
Blocked by: 01
Blocks: 09

## Question

How does usefulness of Form 8-K Item 5.02 (and ambiguous-item 8-Ks) decay for
agent `EMPLOYED_BY` temporal updates versus older event archaeology — and is
**one year** before watermark a sound agent window?

## Exit criteria

- Why recent 5.02 events matter more than multi-year 8-K history given proxy
  baselines.
- Recommended agent window; Explore optional extension.
- Confirm unrelated 8-Ks stay out of bulk download.

## Answer

**Gist:** Item 5.02 is a short-horizon **delta** on top of the proxy employment
baseline. Multi-year 8-K history is mostly event archaeology; once later proxies
re-baseline officers, old appointments/departures do not improve agent
current-at-watermark open versions. One year covers a full proxy-cycle gap for
intra-year join/leave/role changes. Unrelated 8-Ks (items prove no 5.02) stay
out of bulk download (`not_applicable` from metadata).

**Recommended agent window:** filing date ≥ **`W − 1 year`** for `8-K` /
`8-K/A` with Item 5.02 **or** missing/ambiguous items.  
**Explore:** optional deeper 5.02 archive, labeled not agent-grade.

**Research:** [../research/04-item-502-usefulness.md](../research/04-item-502-usefulness.md)
