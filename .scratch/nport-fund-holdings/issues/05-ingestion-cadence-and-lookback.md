Type: grilling
Status: open

Blocked by: 01, 02

## Question

What ingestion cadence and historical lookback window should this
dataset use?

**Corrected framing (this ticket's own original Question was wrong on
the current baseline -- Ticket 02 corrected it during research):**
N-PORT is filed and publicly disclosed **quarterly today**, not monthly
-- the 2024 rule's monthly-filing/monthly-disclosure regime has been
delayed twice (large fund groups to Nov 17 2027, smaller groups to May
18 2028) and a Feb 18 2026 SEC proposal would make quarterly-only public
disclosure *permanent* even once monthly (non-public) filing eventually
starts. Current public volume is ~52,000 filings/year (~13,000/quarter),
not the ~156,000/year a monthly assumption would produce. So the real
open questions are: (a) design ingestion around the current, live
quarterly regime as the baseline (matching this session's "real
measurements, not estimates" standing preference, and Ticket 02's own
finding that near-term monthly disclosure is unlikely), with cadence/
schema flexible enough to absorb monthly *if and when* it eventually
takes effect; (b) what historical lookback window to backfill (N-PORT
data exists back to Oct 2019 per SEC's own Data Sets page -- full
history vs. a bounded window analogous to 13F's
`DEFAULT_FUNDAMENTALS_LOOKBACK_YEARS=2` is a real cost/completeness
tradeoff given Ticket 02's ~65M-175M cumulative-row estimate).

## Answer

(not yet resolved)
