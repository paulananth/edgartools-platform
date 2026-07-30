# 08 — Free/legal full-text earnings-call transcript content sources

Type: research
Status: resolved
Blocked by: none

## Question

`TRANSCRIPT_EVENTS`' earnings-preview and initiating-coverage promotion tiers (ticket 06 §7, corrected 2026-07-27) are blocked on transcript **content**, not on ingest code — `store_transcript_text` already accepts arbitrary quarters per CIK, but requires the real transcript text, and no first-party source exists (Apple's own `investor.apple.com`/newsroom publishes only a results press release plus a ~2-week audio/video webcast replay, no transcript text — checked live 2026-07-27). Every real transcript text found in a first search pass (Investing.com, Seeking Alpha, Yahoo Finance, Motley Fool, Morningstar) is a third-party licensed re-transcription.

Following the ticket 07 model (free EARNINGS_CALENDAR sources): is there **any** free, ToS-clean, bulk-or-per-request, official/documented source of full earnings-call transcript text — official or licensed-for-redistribution — that this platform could legally ingest via `store_transcript_text`? Specifically check:

- Does any issuer other than Apple routinely publish official prepared-remarks/Q&A transcript text on its own IR site (first-party, no licensing question)? If pilot CIKs stay Apple-only this doesn't help, but it's relevant if `PILOT_CIKS` is ever revisited.
- Do any of the major transcript aggregators (Seeking Alpha, Motley Fool, Investing.com, roic.ai, Morningstar) offer a free tier or API with redistribution rights in their terms of service — not just free *reading*, but free *storage/reproduction* — the same ToS-clean bar ticket 07 applied to Alpha Vantage?
- Does SEC EDGAR itself ever contain call transcript text as a filing exhibit (e.g. some issuers file transcripts or investor-day materials as 8-K exhibits)? This platform already has full EDGAR access; if any material fraction of the pilot's target issuers do this, it would be a zero-new-integration source.
- Confirm whether audio-only replay sources (Apple's webcast) have any documented, ToS-clean speech-to-text pathway this platform could run itself on official audio (as opposed to using someone else's re-transcription) — and if so, whether that is realistically in scope for an Explore-tier pointer product or is its own, larger build.

Report per-source: is it free, is it ToS-clean for storage/redistribution (not just personal reading), is it official/documented, and what quarters/coverage it could realistically provide for CIK 320193 (Apple) specifically, since that remains the locked pilot universe.

## Answer

**No source clears all three bars (free + ToS-clean-for-redistribution + official/documented)
for transcript TEXT** — a different outcome from sibling ticket 07's Alpha Vantage finding for
calendar dates. Full findings, per-source verdict table, and primary-source citations (live
ToS pages, a fetched commercial transcript PDF, SEC EDGAR full-text search API, live IR pages):
[`08-research-findings.md`](08-research-findings.md).

Per the four checks this ticket asked for:

1. **Apple's own IR site**: re-confirmed live 2026-07-28 — press release + ~2-week audio/video
   replay only, no transcript text anywhere, including the canonical `apple.com/investor/earnings-call/`
   page. **Other issuers** (Coca-Cola, Booking Holdings, SEI, Apollo, etc.) do IR-host PDF
   transcripts, but every one checked is copyrighted by a third-party vendor (FactSet CallStreet,
   LLC) — first-party hosting does not clear the redistribution bar. One narrow exception: IBM
   self-authors "Earnings Prepared Remarks" 8-K exhibits with no vendor copyright, but it stops
   before Q&A begins and doesn't exist for Apple.
2. **Aggregators** (Seeking Alpha, Motley Fool, Investing.com, Morningstar): all personal/
   non-commercial-only ToS with explicit anti-scraping/anti-redistribution clauses (quoted
   verbatim in the findings file); none has an official public API. **roic.ai** is the closest
   analog to Alpha Vantage (genuine free-tier API with an actual transcript endpoint) but its ToS
   explicitly bars redistribution/resale without authorization.
3. **SEC EDGAR 8-K exhibits**: confirmed via direct EDGAR full-text-search counts that
   transcript-as-exhibit filing is rare (~22-52 hits across all US issuers over 2 years, not the
   "20-30%" secondary-source figure the research disproved), and Apple has never done it. Even
   when present, the content is still third-party (FactSet CallStreet) copyrighted — not released
   into the public domain by being filed — so it isn't the zero-licensing-question fallback the
   ticket speculated it might be.
4. **Apple webcast audio + self-run speech-to-text**: Apple's own Website Terms of Use bar
   copying/automated access to site content without written consent — not ToS-clean — and would
   in any case be a materially larger, differently-shaped build (ASR pipeline, diarization,
   ongoing cost/maintenance) than an Explore-tier pointer product.

**This is a hard blocker, not a hedge**, and it's broader than ticket 06 originally scoped: ticket
06 framed the content gap as blocking only the earnings-preview/initiating-coverage tiers, but
this research shows criterion 3 (real content via `store_transcript_text`, not a bare pointer) is
also required for the earnings-analysis Covered tier that ticket 06 called "structurally
satisfiable Apple-only" — that satisfiability was conditional on a content source existing, and
none does for free. All three consuming-skill tiers are blocked identically until one of exactly
two routes is taken: (a) license a vendor (FactSet CallStreet directly, roic.ai's paid enterprise
tier, or similar) under a licensing decision this platform hasn't made, or (b) accept
`firm_manual` populated by a human with actual usage rights to the text they enter. Both routes
are ops/business decisions downstream of this map, not wayfinding decisions this ticket or map
need to make — same class as the Finnhub license gate already recorded in this map's Out of
scope section.
