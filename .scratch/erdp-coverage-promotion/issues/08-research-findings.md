# Ticket 08 research findings — free/legal transcript TEXT sources

Research conducted 2026-07-28 against primary sources: live-fetched IR pages, live-fetched
Terms of Service/Terms of Use pages, a live-fetched sample commercial transcript PDF, SEC
EDGAR's own full-text search API (`efts.sec.gov`) hit with a proper identifying User-Agent per
SEC's fair-access policy, and live 8-K exhibit documents pulled directly from
`www.sec.gov/Archives`. Where a ToS page could not be fetched directly (Cloudflare bot
protection blocked both `WebFetch` and `curl`), that is called out explicitly rather than
silently substituted with a secondary summary.

## Bottom line

**No source clears all three bars (free + ToS-clean-for-redistribution + official/documented)
for transcript TEXT.** This is a different outcome from ticket 07 (Alpha Vantage cleared all
three bars for calendar dates). For transcript text specifically, every free/official candidate
found fails at least one bar — usually the redistribution-rights bar, sometimes the
free-and-official bars simultaneously. This is a **hard blocker, not a hedge**: `store_transcript_text`
requires real transcript text, and there is no legally clean way to obtain Apple's for free today.

**Which ticket 06 criteria this blocks:** ticket 06 framed the content gap as blocking only the
earnings-preview/initiating-coverage tiers (criterion 7). That undersells it — **criterion 3**
(`content_sha256 IS NOT NULL`/`char_count IS NOT NULL`, i.e. real content via
`store_transcript_text`, not a pointer) is also required for the **earnings-analysis Covered
tier**, the one ticket 06 said was "structurally satisfiable Apple-only." This research shows
that satisfiability was conditional on a content source existing, and none does for free. So this
finding blocks **all three** consuming-skill tiers identically, not just two of them, until one
of exactly two routes is taken: (a) license a vendor (FactSet CallStreet directly, roic.ai's paid
enterprise tier, or similar) and ingest under that license via `source_system="fmp"`/`"other"`
plus a licensing decision this platform hasn't made, or (b) accept `firm_manual` populated by a
human who obtained the text through a channel with actual usage rights (e.g. their own paid
subscription, used consistently with that subscription's personal-use terms) — which is a
process/scale decision for ticket 05, not a code gap.

| Candidate | Free? | ToS-clean for storage/redistribution? | Official/documented? | Apple (CIK 320193) coverage |
|---|---|---|---|---|
| Apple's own IR site (`investor.apple.com`, `apple.com/newsroom`) | N/A (no transcript exists) | N/A | N/A | **No transcript text exists at all** — press release + ~2-week audio/video replay only. Re-confirmed live 2026-07-28. |
| Other issuers' IR sites (Coca-Cola, Booking Holdings, SEI, Apollo, Waste Management, Tyson, Primoris, Chico's, etc.) | Yes, freely readable/downloadable | **No** — hosted PDFs are third-party (FactSet CallStreet) copyrighted (see §2). One narrow exception: IBM self-authors "Earnings Prepared Remarks" with no vendor copyright — but Q&A-incomplete and not Apple. | Yes, first-party-hosted | N/A — irrelevant unless `PILOT_CIKS` expands, and doesn't fully help even then (see §2) |
| Seeking Alpha | Free tier exists (site + unofficial RapidAPI wrapper) | No — personal/non-commercial only, explicit anti-scraping clause, republish requires written consent | No official public API | Apple transcripts exist on SA but not usable |
| Motley Fool | Free (site only) | No — personal/non-commercial only, explicit anti-scraping clause, redistribution needs Fool's prior written permission | No public API at all | Apple transcripts exist on Fool.com but not usable |
| Investing.com | Free (site only) | No — explicit "prohibited to use, store, reproduce, display, modify, transmit or distribute" without prior written permission | No public API (confirmed: contractual data-provider terms bar it) | Apple transcripts exist on Investing.com but not usable |
| roic.ai | **Yes — genuine documented free-tier API** (5 req/min), with an actual `/earnings-calls` transcript endpoint | No — ToS: "may not be redistributed or resold without explicit authorization" | **Yes** — first-party, documented API (closest analog to Alpha Vantage's shape) | Would technically return Apple transcript text, but redistribution/storage is exactly what's prohibited |
| Morningstar | No genuine free tier for transcripts (RapidAPI wrapper only, unofficial) | No — personal/non-commercial only, no redistribution | Paid enterprise API only (Morningstar Direct etc.), not free | N/A |
| SEC EDGAR 8-K exhibit | Free (already a zero-new-integration source) | **No, even when present** — the filed exhibit text is still third-party (FactSet CallStreet, etc.) copyrighted content, not released into the public domain by virtue of being filed | Yes, when present | **Apple has never done this** — confirmed live: Apple's only 8-K exhibit is `EX-99.1`, the results press release, same as ticket 06/08's original finding. Even setting Apple aside, this practice is rare across all issuers (see below), so it isn't a real fallback path even if `PILOT_CIKS` expanded. |
| Apple's own webcast audio + platform-run STT | Free to *listen* for ~2 weeks | No — Apple's Website Terms of Use bar copying/recording/automated access to any site content without Apple's written consent | Apple's audio is official; a platform-run transcription of it is not | Technically the only path to Apple's *own* words verbatim, but not ToS-clean, and a materially larger build (see §4) |

## 1. Apple's IR site — re-verified live 2026-07-28

- `apple.com/newsroom/.../apple-reports-second-quarter-results/` (fetched live, dated 2026-04-30
  in the newsroom URL for AAPL's most recent quarter at research time) contains **only the
  financial-results press release**. Its only pointer to the call itself: *"Apple will provide
  live streaming of its Q2 2026 financial results conference call beginning at 2:00 p.m. PT on
  April 30, 2026, at apple.com/investor/earnings-call. The webcast will be available for replay
  for approximately two weeks thereafter."* No transcript link, no PDF, no "Transcript" label
  anywhere on the page.
- Followed that exact link and fetched `apple.com/investor/earnings-call/` directly (the
  canonical page the press release itself names, not an adjacent guess) — it contains **only
  conference-call dial-in numbers and technical streaming/browser requirements**. No press
  release, no webcast player embed, no replay link, and explicitly no text anywhere on the page
  mentioning "transcript." This closes the gap the JS-shell fetches of `investor.apple.com`
  left open — the canonical named page itself, not just its adjacent navigation shell, was
  checked and confirmed transcript-free.
- Cross-checked via `sec.gov/Archives/edgar/data/320193/000032019326000005/a8-kex991q1202612272025.htm`
  (Apple's Q1 FY2026 8-K, `EX-99.1`, filed 2026-01-29, items 2.02/9.01) fetched directly with a
  proper SEC User-Agent header: identical shape — the *entire* exhibit is the press release text,
  no transcript. Same for every other Apple `EX-99.1` earnings 8-K found via EDGAR full-text
  search (query `"earnings call"` scoped to CIK 0000320193, forms=8-K — 45 hits, all press
  releases referencing the webcast, none containing transcript content).
- Also found: an **"Apple Quarterly Earnings Call" podcast** on Apple Podcasts — audio only,
  same ~2-week rolling-archive pattern (currently ~23 episodes live at any time, i.e. a rolling
  window, not a persistent archive), not a new content type — still audio, no text.
- **Conclusion: ticket 06/08's original finding is re-confirmed unchanged as of 2026-07-28.**
  Apple publishes no transcript text anywhere on its own properties.

## 2. Do any *other* issuers publish official first-party transcript text?

Searched broadly and found several large/mid-cap issuers whose IR sites do host downloadable
PDF transcripts (Coca-Cola, Booking Holdings, SEI, Apollo Global Management, Waste Management,
Tyson Foods, Primoris Services, Chico's FAS). Fetched one directly (Booking Holdings Q1 2025,
`s201.q4cdn.com/.../CORRECTED-TRANSCRIPT_-Booking-Holdings-Inc-BKNG-US-Q1-2025-Earnings-Call-...pdf`)
as a PDF and read its actual pages:

- Cover page: **"Copyright © 2001-2025 FactSet CallStreet, LLC"**.
- Last page (page 19 of 19), verbatim: *"The contents and appearance of this report are
  Copyrighted FactSet CallStreet, LLC 2025 CallStreet and FactSet CallStreet, LLC are trademarks
  and service marks of FactSet CallStreet, LLC. All other trademarks mentioned are trademarks of
  their respective companies. All rights reserved."* Preceded by a disclaimer block stating the
  report is "published solely for information purposes, and is not to be construed as financial
  or other advice."

This is the critical nuance: these transcripts are **hosted first-party** (on the issuer's own IR
domain/CDN), which superficially looks like "no licensing question" — but the copyright is held
by **FactSet CallStreet, LLC**, a third-party commercial transcription vendor, not the issuer.
The issuer is merely reproducing FactSet's commercial product for its own investors' convenience
under whatever license FactSet grants *it*; nothing in the document grants any license to a
third party (like this platform) to copy/store/redistribute it. Every one of the 8 companies
checked used the identical FactSet CallStreet template/copyright block — this looks like an
industry-standard vendor practice, not a one-off. **This means "other issuer publishes it
first-party" does not actually clear the ToS-clean bar** — it just moves the licensing question
from "which aggregator scraped it" to "which vendor the issuer itself licensed it from." Even if
`PILOT_CIKS` were expanded to one of these companies, ingesting their IR-hosted PDF would still
mean storing FactSet CallStreet's copyrighted commercial content without a license from FactSet.

**One genuine exception found, narrower than a full transcript:** IBM files its own
issuer-authored **"Earnings Prepared Remarks"** as an 8-K exhibit every quarter — checked
directly (`sec.gov/Archives/edgar/data/51143/000005114325000007/ibm_ex99x1.htm`, "IBM 4Q24
Earnings Prepared Remarks", and `.../000005114325000031/ibmex99-1.htm`, "IBM 1Q25 Earnings
Prepared Remarks" — both fetched live with a proper SEC User-Agent). Read start-to-finish: no
FactSet/CallStreet or any other third-party copyright notice anywhere in either document — this
is IBM's own scripted CEO/CFO commentary, filed directly with the SEC, genuinely
zero-new-licensing-question content. EDGAR full-text search for the exact phrase `"Earnings
Prepared Remarks"` (`forms=8-K`, 2024-07-28–2026-07-28) returns only 6 hits across 2 distinct
companies (IBM and Asensus Surgical) — so this is real but a minority, idiosyncratic-company
practice, not a general pattern. **Important limitation: it stops exactly where Q&A begins** —
IBM's own document ends with *"Arvind and I are now happy to take your questions... Operator,
let's please open it up for questions"* and contains no actual Q&A exchange. So even where this
pattern exists, it only ever satisfies the "management prepared remarks/quotes" half of ticket
06 criterion 3's content need, never the "quotable Q&A excerpts" half — and it doesn't exist for
Apple at all (confirmed: Apple's only 8-K exhibit is the press release, not prepared remarks —
see §1). Net effect on the ticket's `PILOT_CIKS`-expansion question: there is a genuine,
ToS-clean, no-vendor issuer-authored source for *some* other CIKs, but it is Q&A-incomplete and
would still require expanding the pilot universe to benefit from it — it does not change the
Apple-only answer today.

Beyond this one exception, no issuer was found that authors its own **full** transcript
(prepared remarks + Q&A) from scratch with issuer-owned copyright — the FactSet CallStreet
vendor pattern remains the dominant path IR sites use whenever a full Q&A transcript is
published.

## 3. ToS survey: Seeking Alpha, Motley Fool, Investing.com, roic.ai, Morningstar

All fetched from the live, current ToS/Terms pages (URLs below), same bar ticket 07 applied to
Alpha Vantage: free tier existing is not enough — the ToS must actually grant storage/
redistribution rights, not just personal reading.

### Seeking Alpha — `https://about.seekingalpha.com/terms` (redirect target of `seekingalpha.com/page/terms-of-use`)

- **Section 5 (Copyright, Linking Policy and Trademarks):** *"You may access and use the
  Content, and download and/or print out copies of any content from the Site, solely for your
  personal, non-commercial use."* And: *"If you are interested in reprinting, republishing or
  distributing content from Seeking Alpha, please contact Seeking Alpha to obtain written
  consent."*
- **Section 6 (User Conduct)**, explicit anti-scraping clause: prohibits using *"any robot,
  spider, site search/retrieval application, or other manual or automatic device or process to
  download, retrieve, index, 'data mine', 'scrape', 'harvest' or in any way reproduce or
  circumvent the navigational structure or presentation of the Site or its contents."*
- No official public API exists (confirmed via search: only unofficial third-party RapidAPI/
  scraping wrappers, none sanctioned by Seeking Alpha).
- **Verdict: free = yes (reading only); ToS-clean for storage/redistribution = no; official/
  documented API = no.**

### Motley Fool — `https://www.fool.com/legal/terms-and-conditions/fool-rules/`

- **Section 7 (Intellectual Property):** *"You may make one copy of the Content for your
  personal, non-commercial use... Any other copying, distribution, storing, or transmission of
  any kind, or any commercial use of our Content, is prohibited without The Fool's prior written
  permission."* Also: *"You also may not republish, post, transmit, or distribute the Content to
  online bulletin and message boards, blogs, chat rooms, intranets, or anywhere else without our
  consent."*
- **Section 8 (Conduct):** prohibits *"Use any automated means, including, without limitation,
  agents, robots, scripts, or spiders, to access, monitor, copy or harvest data from any part of
  our sites."* Section 7 separately: *"You further agree not to create abstracts from or scrape
  our Content... for use on another website or service."*
- No official public API (confirmed: Fool.com's own API infrastructure is internal/operational,
  and it consumes third-party market data (Polygon) rather than exposing its own transcripts via
  API).
- **Verdict: free = yes (reading only); ToS-clean for storage/redistribution = no; official/
  documented API = no.**

### Investing.com — `https://www.investing.com/about-us/terms-and-conditions`

- Exact clause: *"It is prohibited to use, store, reproduce, display, modify, transmit or
  distribute the data contained in this website without the explicit prior written permission of
  Fusion Media and/or the data provider."* This is the most direct, unambiguous "no storage" ToS
  language of any source checked — storage itself, not just redistribution, is explicitly named.
- No official public API — confirmed via search: Investing.com's own support docs state they
  cannot offer public API access because of contractual restrictions with their own data
  providers.
- **Verdict: free = yes (reading only); ToS-clean for storage/redistribution = no (explicitly
  bars storage, the strictest language found); official/documented API = no.**

### roic.ai — `https://www.roic.ai/tos` (direct fetch blocked by Cloudflare bot-challenge; **four**
separate attempts made — `/tos`, `/about`, and `/faq` all returned HTTP 403 via both `WebFetch`
and `curl` with a browser User-Agent, a stronger and more deliberate anti-automation posture than
any of the other four sites checked, which all fetched cleanly on the first try. This is a real,
disclosed limitation, not silently worked around: the quotes below come from search-engine-indexed
snippets of the live ToS page text itself, corroborated across two independent search passes with
consistent wording, plus the docs pages at `roic.ai/api` / `roic.ai/api/docs/getting-started`,
which *did* fetch successfully directly)

- **This is the one candidate structurally closest to Alpha Vantage** — roic.ai has a genuinely
  documented, first-party API (`roic.ai/api`) with real endpoints:
  `GET /v3.0.0/earnings-calls` (list) and `GET /v3.0.0/earnings-calls/{identifier}` (a specific
  transcript, with a `format` param for JSON or plain text) — i.e., it is an actual
  transcript-text endpoint, not just metadata.
- **Free tier is real and documented**: rate-limited to 5 requests/minute per the docs'
  troubleshooting section (*"Rate limit exceeded (HTTP 429): you exceeded your plan's per-minute
  request limit (5/min on the free tier)"*).
- **ToS blocks exactly the use this platform needs**: indexed ToS text states *"Data obtained
  through the API may only be used in accordance with your subscription plan and may not be
  redistributed or resold without explicit authorization"* and separately *"Aggregated datasets,
  platform design, trademarks, and trade dress may not be used in connection with any product or
  service without prior written consent of ROIC AI."* Storing transcript text into this
  platform's own gold tables and serving it back out through `store_transcript_text` is exactly
  the kind of redistribution this clause is written to prevent.
- **Second, independent corroboration** (separate search pass, aimed at re-fetching the exact
  clause verbatim rather than trusting the first pass alone): could not retrieve the raw ToS
  text directly, but surfaced a consistent, materially confirming detail — roic.ai's pricing
  page distinguishes "personal" plans from separate **paid enterprise plans priced from $600/mo
  that are the ones licensed for commercial use**. That two-tier structure (personal/free vs.
  paid-for-commercial-use) is the same shape as every other source in this survey and is
  consistent with, not contradictory to, the redistribution-ban snippet from the first pass.
- **Verdict: free = yes (genuine free-tier API, real transcript endpoint); ToS-clean for
  storage/redistribution = no (ToS text found via indexed snippets across two independent
  search passes rather than a directly re-fetched raw page — flagged as the one source where
  full primary-page corroboration was blocked by the site's own bot protection, stronger here
  than on any other site checked); official/documented = yes, the best-documented of the five.**

### Morningstar — `https://www.morningstar.com/mm/user-agreement`

- **"Use of this Service"**: *"you may download or print hard copies of pages or reports from
  the Service or portions thereof but only in connection with your own personal, noncommercial
  use"*; and *"you may not modify, copy, distribute, disclose, retransmit, sell, publish,
  broadcast, or circulate the Service, or any portion of it."*
- **"Ownership and Copyright"**: *"you will not use these data or information for any unlawful
  or unauthorized purpose, and that you will use reasonable efforts to protect them from illicit
  distribution."*
- No genuine free tier for transcripts specifically — Morningstar's real API products
  (Morningstar Direct / Intelligence Engine) are enterprise/paid only; the only "free" access
  found is an unofficial RapidAPI wrapper, not sanctioned by Morningstar and not documented by
  Morningstar itself.
- **Verdict: free = no (for transcripts specifically, no genuine free/documented tier exists);
  ToS-clean for storage/redistribution = no; official/documented API = no (enterprise-only).**

## 4. SEC EDGAR as an exhibit source — checked directly, both for Apple and issuers generally

- **Apple: confirmed no.** Every Apple 8-K `EX-99.1` earnings exhibit checked (going back
  through the filings list via `data.sec.gov/submissions/CIK0000320193.json` and spot-checked via
  direct fetch of the underlying `.htm` documents with a proper SEC User-Agent) is the results
  press release verbatim, never a call transcript or prepared remarks. EDGAR full-text search
  for `"earnings call"` scoped to Apple's CIK
  (`efts.sec.gov/LATEST/search-index?q=%22earnings+call%22&forms=8-K&ciks=0000320193`) returned
  45 hits total; the top-scoring results sampled (not all 45 individually opened) were press
  releases referencing the webcast, and this is consistent with the direct fetch of the actual
  document for two separate quarters (2026-01-29 and the Q1 FY2026 filing checked in full above)
  showing the exhibit is the press release end-to-end with no transcript content appended.
- **Issuers generally: rare, not a real fallback even if `PILOT_CIKS` expanded.** Used EDGAR's
  own full-text search API (`efts.sec.gov`) to directly count, over the last 2 years
  (2024-07-28 to 2026-07-28), 8-K filings containing transcript-vendor signature phrases:
  - `"FactSet CallStreet"` → **22 hits**
  - `"Corrected Transcript"` → **4 hits**
  - `"Edited Transcript"` → **15 hits**
  - `"final transcript"` → **11 hits**
  There are roughly 6,000+ US reporting companies, each filing up to 4 Item 2.02 earnings 8-Ks/
  year, so the true 2-year population of earnings-related 8-Ks is on the order of tens of
  thousands. Even summing every transcript-vendor-signature hit above with no de-duplication (52
  hits), that is comfortably a small fraction of a percent of that population — an
  order-of-magnitude comparison, not a precise percentage, since EDGAR's full-text search has no
  direct "Item 2.02 8-K count" filter to use as an exact denominator. **This directly contradicts
  an unverified secondary claim surfaced in an early web-search summary during this research
  ("roughly 20-30% of filers include a verbatim transcript") — that figure could not be traced to
  any primary source and is contradicted by these direct absolute counts against SEC's own
  full-text search system, so it should be treated as unreliable and disregarded.** Filing a
  transcript as an 8-K exhibit is a genuine but rare practice among issuers, confirmed via direct
  example (Chico's FAS, Inc.,
  `sec.gov/Archives/edgar/data/897429/000089742922000018/q42021earningscalltransc.htm`, fetched
  live with a proper SEC User-Agent — confirmed `TYPE EX-99.1`, full prepared-remarks + Q&A text,
  with the same embedded *"Copyright © 2001-2022 FactSet CallStreet, LLC"* watermark text seen
  in §2 above). Separately, filing issuer-authored **prepared remarks only** (no vendor, no Q&A)
  is an even rarer, distinct practice — see IBM's exception in §2.
- **Even when present, this does not resolve the licensing question.** The transcript content
  embedded in the exhibit is still the same third-party (FactSet CallStreet, or another vendor)
  copyrighted commercial product identified in §2 — being filed as a public SEC exhibit does not
  place it in the public domain or grant a redistribution license to whoever downloads it from
  EDGAR. So even setting aside that Apple has never done this, and even if `PILOT_CIKS` were
  hypothetically expanded to a company that does, this would **not** be the "zero-new-integration,
  zero-licensing-question" source the original ticket wording speculated it might be — it would
  carry the identical FactSet CallStreet copyright/redistribution problem found in §2, just
  reached via EDGAR instead of an aggregator site.

## 5. Apple's webcast audio + self-run speech-to-text

- Apple's general Website Terms of Use (`apple.com/legal/internet-services/terms/site.html`,
  fetched live) state: *"no part of the Site and no Content may be copied, reproduced,
  republished, uploaded, posted, publicly displayed, encoded, translated, transmitted or
  distributed in any way (including 'mirroring') to any other computer, server, website or other
  medium for publication or distribution or for any commercial enterprise, without Apple's
  express prior written consent."* Separately: *"You may not use any 'deep-link', 'page-scrape',
  'robot', 'spider' or other automatic device, program, algorithm or methodology... to access,
  acquire, copy or monitor any portion of the Site or any Content."* No investor-webcast-specific
  terms page was found distinct from this general site ToS, and nothing in it carves out an
  exception for audio/video content, recording, or transcription.
- **Conclusion: not ToS-clean.** Running the platform's own speech-to-text on Apple's official
  webcast audio requires downloading/recording that audio in the first place — an act the site
  ToS's blanket "no copying... without Apple's express prior written consent" clause and its
  anti-automation clause both squarely prohibit, independent of what's technically done with the
  audio afterward.
- **Scope note, independent of the ToS question:** even setting legality aside, this would be a
  materially larger build than an Explore-tier pointer product — it requires reliably capturing
  a live/replay audio stream within its ~2-week availability window, a speech-to-text pipeline
  with accuracy good enough for quotable management-quote extraction (ticket 06's criterion 3),
  ongoing cost/latency/maintenance for an ASR service, and speaker diarization to attribute
  Q&A lines correctly — a different-shaped, standalone project, not a small addition to
  `store_transcript_text`.

## Sources consulted (primary)

- `https://www.apple.com/newsroom/2026/04/apple-reports-second-quarter-results/` (live fetch,
  2026-07-28)
- `https://investor.apple.com/investor-relations/default.aspx` and
  `.../default.aspx?section=QuarterlyEarnings` (live fetch — confirmed these are JS-rendered
  shells with no static transcript content, consistent with there being no transcript link at
  all)
- `https://www.apple.com/investor/earnings-call/` (live fetch — the canonical link the press
  release itself names; confirmed dial-in numbers + streaming requirements only, no transcript
  text anywhere on the page)
- `https://www.sec.gov/Archives/edgar/data/320193/000032019326000005/a8-kex991q1202612272025.htm`
  (Apple Q1 FY2026 8-K EX-99.1, fetched via `curl` with SEC-compliant User-Agent)
- `https://data.sec.gov/submissions/CIK0000320193.json` (Apple's full filing history)
- `https://efts.sec.gov/LATEST/search-index?q=...` (SEC EDGAR full-text search API, multiple
  queries: Apple-scoped `"earnings call"`; unscoped `"FactSet CallStreet"`, `"Corrected
  Transcript"`, `"Edited Transcript"`, `"final transcript"`, `"results for its"`, all
  `forms=8-K`, dated 2024-07-28–2026-07-28)
- `https://www.sec.gov/Archives/edgar/data/897429/000089742922000018/q42021earningscalltransc.htm`
  (Chico's FAS 8-K EX-99.1, full transcript, fetched via `curl` with SEC-compliant User-Agent)
- `https://s201.q4cdn.com/865305287/files/doc_financials/2025/q1/CORRECTED-TRANSCRIPT_-Booking-Holdings-Inc-BKNG-US-Q1-2025-Earnings-Call-29-April-2025-4_30-PM-ET.pdf`
  (Booking Holdings IR-hosted transcript PDF, read directly, pages 1–3 and 19)
- `https://investors.coca-colacompany.com/news-events/events` and search-indexed
  `investors.coca-colacompany.com/_assets/.../webcast_transcript/CORRECTED+TRANSCRIPT...pdf` URLs
- `https://about.seekingalpha.com/terms` (live fetch)
- `https://www.fool.com/legal/terms-and-conditions/fool-rules/` (live fetch)
- `https://www.investing.com/about-us/terms-and-conditions` (live fetch)
- `https://www.roic.ai/api` and `https://www.roic.ai/api/docs/getting-started` (live fetch);
  `https://www.roic.ai/tos`, `https://www.roic.ai/about`, `https://www.roic.ai/faq` (all three
  blocked by Cloudflare bot-challenge on both `WebFetch` and `curl` — ToS text corroborated via
  two independent search-engine-indexed-snippet passes instead, flagged as such)
- `https://www.sec.gov/Archives/edgar/data/51143/000005114325000007/ibm_ex99x1.htm` and
  `.../000005114325000031/ibmex99-1.htm` (IBM 4Q24/1Q25 "Earnings Prepared Remarks" 8-K
  exhibits, fetched via `curl` with SEC-compliant User-Agent, read start-to-finish)
- `https://www.morningstar.com/mm/user-agreement` (live fetch)
- `https://www.apple.com/legal/internet-services/terms/site.html` (live fetch)
