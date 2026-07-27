# 08 — Free/legal full-text earnings-call transcript content sources

Type: research
Status: open
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

*(unresolved)*
