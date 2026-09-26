# Can SEC artifact parsing move to Rust?

Date: 2026-09-25
Reviewed for Codex check-in: 2026-09-26.
Repository findings and line references were captured on `b4faa6ac`; they
are a dated snapshot, not a claim about every later source change. The
13F Source Contract and timing prototype are separate work in
`codex/heavy-parse-rules`. This note itself contains no timing experiment.
Scope: the parse paths in this checkout that turn SEC and related artifact
bytes into rows, and whether a maintained Rust library can parse those byte
formats. The question is per family. It is not a proposal to rewrite the
warehouse.

## Executive conclusion

Yes. The mechanical formats this platform actually reads can be parsed in
Rust with maintained libraries: XML with quick-xml, JSON with serde_json,
CSV with the csv crate, and browser HTML with html5ever (scraper adds
queries) or the separate streaming parser lol_html. That is a statement about byte formats,
not about replacing the parsers.

The advantage is not the same for every family. A Rust port helps only
where the bytes are large, the parse is repeated, and the rules are
mechanical. Most of the work in this repo sits after the bytes have been
tokenized: name reversal, the individual-filer classifier, footnote
markers, 13F unit and security-class rules, ADV column and date policy,
compensation-table selection and name repair, iXBRL hidden-content
stripping, auditor-signature windows, and spaCy over Item 5.02 prose.
Those stay in Python, including the calls into the edgartools package,
unless a measurement shows the bytes themselves are the cost. No such
measurement was run for this note.

HTML is the family where a Rust XML parser is the wrong tool. SEC filing
HTML, including DEF 14A proxies, 8-K earnings exhibits, 10-K iXBRL, Exhibit
21, and filing-text extraction, is HTML syntax. The HTML Standard treats
that as a different concrete syntax from XML: minor syntax errors are
ignored in HTML and fatal in XML, and namespaces cannot be represented in
the HTML syntax. This repo already parses those documents with HTML
parsers (BeautifulSoup's `html.parser`, or `lxml.html`), not with an XML
parser. quick-xml will not do that job.

The one place the bytes are clearly large is GLEIF, and that reader already
streams. The one place a whole document is materialized before any rule
runs is SEC companyfacts JSON. Neither fact, by itself, justifies a port.

This note separates confirmed repository and library facts from inference.
It is research only; no implementation was performed.

## What "parsing" means here

`get_parser` dispatches four per-filing families and nothing else:
ownership, ADV, proxy, and 8-K earnings
(`edgar_warehouse/parsers/__init__.py:21-30`). 13F and companyfacts are
called from other commands because the holdings live in an attachment and
companyfacts is one JSON document per CIK, not one filing
(`edgar_warehouse/parsers/__init__.py:15-18`). Other families live under
`edgar_warehouse/application/`, `edgar_warehouse/loaders/`,
`edgar_warehouse/mdm/clean/`, and `edgar_warehouse/filing_text_projection.py`.
`scripts/batch/` calls `filing.xbrl()` (`scripts/batch/batch_test_xbrl.py:38`)
and `from edgar.xbrl import XBRL`
(`scripts/batch/batch_financials_10Q.py:2`). Those scripts are not the
warehouse runtime. The warehouse financial path reads SEC's companyfacts
JSON, not an XBRL instance.

The locked edgartools version in this checkout is 5.30.0
(`uv.lock:655-656`), against a floor of `edgartools>=5.29.0`
(`pyproject.toml:16`). Direct parser dependencies of this repo include
`lxml` and `ijson` on the MDM extras (`pyproject.toml:48-49`,
`pyproject.toml:61-62`) and spaCy for Item 5.02 (`pyproject.toml:28-29`).
BeautifulSoup is imported by this repo's HTML parsers and is pulled in
because edgartools 5.30.0 depends on it (`uv.lock:659`).

## Confirmed parse inventory

| Family | Entry | Bytes | Who tokenizes | Source contract |
| --- | --- | --- | --- | --- |
| Forms 3/4/5 | `parse_ownership` (`ownership.py:71`) | SGML-wrapped or bare `ownershipDocument` XML | local `xml.etree` (`ownership.py:261-276`); name reversal and individual classification call edgartools (`ownership.py:47-48`, `ownership.py:113`, `ownership.py:247`) | yes: `format: xml`, `envelope: sgml_text` (`.scratch/source-contract/prototype/sources/form345/contract.yaml:9-12`); two custom steps still call edgartools (`form345/custom.py:9-10`, `form345/custom.py:33-42`) |
| 13F information table | `parse_thirteenf` (`thirteenf.py:115`) | information-table XML | edgartools `parse_infotable_xml` (`thirteenf.py:140`), which uses `lxml.etree` (installed `edgar/thirteenf/parsers/infotable_xml.py:4`, `infotable_xml.py:30`) | no |
| 13F cover | `parse_thirteenf_cover` (`thirteenf_cover.py:17`) | cover XML | local `ElementTree.fromstring` (`thirteenf_cover.py:18`) | no |
| Per-filing ADV | `parse_adv` (`adv.py:31`) | XML, HTML, text, or a PDF sniff | local BeautifulSoup, `"xml"` only when the sniff says XML, otherwise `"html.parser"` (`adv.py:38-39`, `adv.py:74-84`); the rest is tag lists and regex | no. The spec's "ADV parser (CSV)" is a different shape; see below |
| IAPD ADV bulk | `parse_adv_bulk_archive` (`adv_bulk_ingest.py:103`) | ZIP of CSV, decoded as cp1252 (`adv_bulk_ingest.py:66`) | local `csv.DictReader` plus date and amount rules (`adv_bulk_ingest.py:71-100`) | trial round 3 is `format: csv` (`.scratch/source-contract/trial/round-3/adv-adviser/contract.yaml:8`). Not the production `parse_adv` |
| Firm roster | `parse_firm_roster_archive` (`adv_firm_roster_ingest.py:115`) | ZIP of a wide CSV, cp1252 (`adv_firm_roster_ingest.py:65`) | local `csv.DictReader`; about eight columns of a 448- or 171-column file are kept (`adv_firm_roster_ingest.py:8-10`, `adv_firm_roster_ingest.py:25-27`) | no |
| Firm-roster listing page | `parse_firm_roster_listing` (`firm_roster_fetch.py:62`) | HTML listing | two regular expressions over link text (`firm_roster_fetch.py:35-41`), not a DOM | no |
| ADV reports metadata | `parse_reports_metadata` (`adv_bulk_fetch.py:43`) | small JSON object | `json.loads` then filename regex (`adv_bulk_fetch.py:52-68`) | no |
| Companyfacts | `parse_entity_facts` (`financials.py:57`) | SEC companyfacts JSON, one object per CIK | `json.loads` in the gateway (`edgartools_sec_gateway.py:214`) or in acceptance (`company_facts_silver_acceptance.py:185`); this function only walks an already-built dict | no |
| Derived financials | `compute_derived_for_accession` (`financials_derived.py:175`) | no artifact bytes | arithmetic over fact rows the module itself calls "computations over extracted facts, not extractions" (`financials_derived.py:3-8`) | no |
| Accounting flags | `score_accounting_flags` (`accounting_flags.py:46`) | no artifact bytes | cross-period formulas over derived rows (`accounting_flags.py:1-10`) | no |
| DEF 14A compensation | `parse_proxy_fundamentals` (`proxy_fundamentals.py:416`) | primary-document HTML | `lxml.html.fromstring` then edgartools `extract_summary_compensation` (`proxy_fundamentals.py:441-453`); this repo then repairs names (`proxy_fundamentals.py:59-67`, `proxy_fundamentals.py:464`) | explicitly out of scope; see below |
| 8-K earnings and guidance | `parse_earnings_release` (`earnings_release.py:45`) | HTML of the 8-K or EX-99.1 | edgartools `EarningsRelease`, which calls `parse_html` (`earnings_release.py:83`; installed `edgar/earnings.py:992-998`). `parse_html` uses `lxml.html.fromstring` with `recover=True` (`edgar/documents/parser.py:177-191`). Guidance rows are a second heuristic pass (`earnings_release.py:153-170`) | no |
| Item 5.02 | `parse_item_502` (`item_502.py:524`) | 8-K HTML or text, tags stripped by regex (`item_502.py:165-177`) | spaCy `en_core_web_sm` (`item_502.py:158-162`) plus a few regexes (`item_502.py:531-542`) | no |
| Filing text | `extract_text_for_accession` (`filing_text_projection.py:56`); normalize at `filing_text_projection.py:156` | `.htm`/`.html`, `.xml`, or other bytes | BeautifulSoup `"html.parser"` or `"xml"` (`filing_text_projection.py:158-164`), then iXBRL header and `display:none` stripping (`filing_text_projection.py:136-153`) | no |
| Exhibit 21 / 20-F Exhibit 8 | `parse_subsidiary_exhibit` (`subsidiary_exhibits.py:48`) | HTML or plain text | BeautifulSoup `"html.parser"` (`subsidiary_exhibits.py:65`, `subsidiary_exhibits.py:73`); table-header heuristics | no |
| Auditor evidence | `parse_auditor_evidence` (`auditor_evidence.py:86`) | annual-filing HTML, often with iXBRL facts | BeautifulSoup `"html.parser"` (`auditor_evidence.py:104`); concept `name` attributes, else a bounded signature regex (`auditor_evidence.py:146-168`) | no |
| PCAOB firm registry | `parse_pcaob_firm_registry` (`auditor_evidence.py:193`) | CSV | `csv.DictReader` (`auditor_evidence.py:198`) | no |
| Submissions JSON | `stage_company_loader` and siblings (`bronze_submission_extractors.py:65`) | SEC submissions JSON | `json.loads` (`submissions_silver_acceptance.py:332`, `edgartools_sec_gateway.py:214`); `is_individual_filer` is a rule over the dict (`bronze_submission_extractors.py:38-62`) | lookup input to the Form 3/4/5 contract, not its own prototype contract |
| Daily form index | `stage_daily_index_filing_loader` (`bronze_daily_index_extractors.py:17`) | fixed-width text lines | one regex (`bronze_daily_index_extractors.py:9-11`, `bronze_daily_index_extractors.py:32`) | no |
| Company tickers | `seed_universe_loader` (`bronze_reference_extractors.py:8`) and `_parse_company_ticker_rows` (`silver_landing_store.py:601`) | SEC ticker JSON, two shapes | dict walk after JSON parse | no |
| GLEIF native | `inspect_archive` (`gleif_source.py:236`) | ZIP member, JSON or XML | streaming: `ijson.basic_parse` (`gleif_source.py:102-103`) or `lxml.etree.XMLPullParser` (`gleif_source.py:167-174`) | prototype reads JSONL, not the zip (`gleif/contract.yaml:7-10`) |
| Text signals | `extract_text_signals` (`text_extractors.py:255`) | plain text, tags already gone (`text_extractors.py:9-11`) | regex | no production caller outside this module and tests |
| Yahoo, Finnhub, Alpha Vantage | `parse_yahoo_consensus_estimate` (`consensus_estimates.py:304`), `parse_finnhub_earnings_calendar` (`earnings_calendar.py:329`), `parse_alphavantage_earnings_calendar` (`earnings_calendar.py:446`) | small JSON or CSV API payloads | field mapping | no |

The Form 3/4/5 "SGML" step is not an SGML parser. Both the production
parser and the prototype take the slice between `<XML>` and `</XML>`,
strip a declaration and control characters, and parse that as XML
(`ownership.py:261-276`; prototype `source_engine.py:210-230`). The header
is lines split on the first colon (`source_engine.py:197-203`).

`financials_derived.py` and `accounting_flags.py` are included so they are
not mistaken for parsers. They do not see artifact bytes.

## What a Source Contract already parses by configuration

The spec's readers are XML, JSON, CSV, and `bytes`
(`docs/specs/source-contract/spec.md:191-196`). The prototype engine
implements those four (`source_engine.py:207-254`). `bytes` means the
engine does not parse; every table must use a custom reader
(`spec.md:196`, `spec.md:428`).

Confirmed prototype coverage:

- Forms 3/4/5: XML plus an SGML envelope, mapped by primitives. The spec
  says that contract was equal to `ownership.py` on 5,356 of 5,356
  artifacts (`spec.md:890-891`). The two values that primitives cannot
  compute, display name and owner kind, are custom steps that import
  `reverse_name` and `_classify_is_individual` (`form345/custom.py:9-10`).
- GLEIF Level 1: JSONL, no custom step. The spec says the worked example
  is 93 lines and was proved on 316 records (`spec.md:885-888`). It also
  says the streaming zip reader was not built (`spec.md:1063-1064`).
- HTML demo: `format: bytes` and a custom reader
  (`html-demo/contract.yaml:7-11`) that uses the standard-library
  `HTMLParser` (`html-demo/custom.py:3`, `html-demo/custom.py:33-36`).
  The spec says this ran on a synthetic 3-row table, not a real DEF 14A
  (`spec.md:1061-1062`).

The spec states the boundary for HTML in its own words. A source whose
artifact has no fixed shape, "an HTML document such as a DEF 14A proxy,
where each company lays its Summary Compensation Table out differently,"
is out of scope for a contract and keeps a hand-written parser. A second
reason given there is state across rows: the name is on the first row of a
block and later rows carry only the wrapped title
(`spec.md:198-208`). The open item that names candidates for a contract
lists the ownership XML parser and the ADV CSV shape, and says the proxy
parser is out (`spec.md:1044-1049`).

That matches the code. `parse_proxy_fundamentals` exists because
`extract_summary_compensation` re-reads the name cell on every row, and
this repo repairs the continuation lines afterward
(`proxy_fundamentals.py:59-67`). Moving that to Rust would move the table
chooser and the repair vocabulary, not a fixed-field decode.

## Rust libraries, from their own docs

Versions below are what the pages returned on 2026-09-25. None of these
numbers are measurements of this repository.

**XML.** quick-xml 0.42.0 describes itself as a high-performance XML
reader and writer with a streaming API based on the StAX model, "suited
for larger XML documents which cannot completely read into memory at
once." The caller asks for the next event. The pull reader is `Reader`
([quick-xml crate docs](https://docs.rs/quick-xml/latest/quick_xml/)).
An `escape-html` feature recognizes HTML5 entities inside `unescape`. That
is entity decoding, not an HTML parser. The same page says quick-xml is
not standard-compliant for encodings that are not ASCII-compatible, and
gives UTF-16 as the example.

**JSON.** serde_json 1.0.151 parses text, a byte slice, or any `io::Read`
into one value, either `serde_json::Value` or a typed structure
([serde_json crate docs](https://docs.rs/serde_json/latest/serde_json/)).
`StreamDeserializer` is a separate iterator: it deserializes a stream into
multiple JSON values, and those values "need to be a self-delineating
value e.g. arrays, objects, or strings, or be followed by whitespace"
([StreamDeserializer](https://docs.rs/serde_json/latest/serde_json/struct.StreamDeserializer.html)).
That is concatenated JSON values. It is not, on that page, a cursor inside
one array. SEC companyfacts is one JSON object
(`financials.py:6-7`). GLEIF's native JSON reader expects one object, a
wrapper key, then an array, and yields array elements with `ijson`
(`gleif_source.py:102-137`). serde_json's documented stream type does not
replace that loop by itself.

**CSV.** The csv crate 1.4.0 provides `Reader` and iterates records, with
Serde support, and is explicit that `ByteRecord` exists for data that may
not be valid UTF-8
([csv crate docs](https://docs.rs/csv/latest/csv/)). That matches the
cp1252 ADV and roster files only after those bytes have been decoded; the
crate does not claim to detect cp1252. This note did not open a ZIP crate.
The ZIP step in this repo is Python `zipfile`
(`adv_bulk_ingest.py:113-115`).

**HTML.** html5ever 0.40.1 is described on its docs.rs page as a
"High-performance browser-grade HTML5 parser." The crate exposes
`parse_document`, `parse_fragment`, a tokenizer module, and a tree-builder
module
([html5ever crate docs](https://docs.rs/html5ever/latest/html5ever/)).
scraper 0.27.0 says it is "an interface to Servo's `html5ever` and
`selectors` crates, for browser-grade parsing and querying," and depends
on `html5ever`
([scraper crate docs](https://docs.rs/scraper/latest/scraper/)). lol_html
3.0.1 describes itself as a low-output-latency streaming HTML
rewriter/parser with a CSS-selector API, "designed to modify HTML on the
fly with minimal buffering," and names `HtmlRewriter` and `rewrite_str`
([lol_html crate docs](https://docs.rs/lol_html/latest/lol_html/)). These
are HTML parsers. They are the Rust counterparts of `lxml.html` and
BeautifulSoup's HTML parser, not of quick-xml.

**XBRL.** A crates.io search for `xbrl` does not come back empty. The
crates.io API returned, among others:

- `xbrl-rs` 0.3.0, updated 2026-05-15, description "XBRL parser and
  validation"
  ([API result](https://crates.io/api/v1/crates?q=xbrl&per_page=20)).
  Its docs say it parses XBRL instance documents, taxonomy schemas, and
  linkbases, and the crate depends on quick-xml
  ([xbrl-rs crate docs](https://docs.rs/xbrl-rs/latest/xbrl_rs/)). The
  documented examples on that page use taxonomy URIs such as
  `de-gaap-ci`. The page does not say it reads SEC companyfacts JSON or
  SEC inline-XBRL HTML.
- `crabrl` 0.1.0, created and updated 2025-08-17, one version,
  description "High-performance XBRL parser and validator," no
  documentation URL in the API record. The HTML page
  `https://crates.io/crates/crabrl` returned only the site title when
  fetched for this note, so nothing further is claimed from it.
- Several crates at `0.1.0-alpha.1`, all created 2026-03-30, sharing the
  description "XBRL parsing, validation, and analysis toolkit" and the
  repository `EffortlessMetrics/xbrlkit`, including `ixhtml-scan`,
  `calc11`, and `archive-zip`. Their READMEs were not opened. They are
  not cited here as parsers this platform could adopt.
- `sec-fetcher` describes an async EDGAR client that fetches filings and
  "XBRL data." That is a client description, and its default version in
  the API result is `0.5.0-alpha`. It was not read as a parser.
- `oim` 0.1.0, created 2017-10-20, "Rust interface onto the Open
  Information Model." One release, nine years old.

This warehouse does not parse XBRL instance XML in production. It parses
companyfacts JSON (`financials.py:5-11`) and, separately, reads a few
iXBRL fact tags out of HTML (`auditor_evidence.py:104-127`,
`filing_text_projection.py:136-153`). An instance-document crate would
not slot into either path without a different ingestion design, which
this note does not make.

**Calling Rust from the current CLI.** PyO3's guide describes it as
"Rust bindings for Python, including tools for creating native Python
extension modules," and shows a `#[pyfunction]` exported into a module
that Python imports
([PyO3 user guide](https://pyo3.rs/)). If a mechanical decoder were ever
worth moving, that is the boundary: a native module called from the
existing Python command, returning rows or events. It is not a reason to
move `reverse_name`, spaCy, or the compensation-table rules. This note
does not design that module.

## HTML is not XML

The HTML Standard, section 1.8, defines two concrete syntaxes for the same
abstract language. HTML is what browsers use for `text/html`. XML is a
different syntax, used when the document is served with an XML MIME type.
The same section explains that XML syntax errors stop rendering, while
HTML error recovery tolerates them. Namespaces are available in XML and
the DOM but cannot be expressed in HTML syntax.
([HTML Standard, 1.8](https://html.spec.whatwg.org/multipage/introduction.html#html-vs-xhtml)).

lxml's own HTML package exists because of that split. `lxml.html` is "a
dedicated Python package for dealing with HTML," and its page says the
HTML parser "notably ignores namespaces and some other XMLisms." It also
says the normal HTML parser handles broken HTML, and that pages far enough
from HTML to be tag soup can still fail
([lxml.html](https://lxml.de/lxmlhtml.html)). The proxy path calls
`lxml.html.fromstring` (`proxy_fundamentals.py:448`). edgartools' earnings
HTML parser does the same with `recover=True`
(`edgar/documents/parser.py:183-191`).

This repo's other HTML entry points use BeautifulSoup's HTML parser, not
its XML parser:

- filing text, for `.htm` and `.html` (`filing_text_projection.py:158-160`);
- per-filing ADV, unless the sniff finds XML-shaped markers (`adv.py:38-39`);
- subsidiary exhibits (`subsidiary_exhibits.py:65`);
- auditor evidence (`auditor_evidence.py:104`).

The XML parser is reserved for documents that are XML: ownership
(`ownership.py:269`), 13F cover (`thirteenf_cover.py:18`), 13F information
tables (edgartools `lxml.etree`, `infotable_xml.py:30`), GLEIF XML
(`gleif_source.py:167`), and filing text whose file suffix is `.xml`
(`filing_text_projection.py:162-164`).

iXBRL makes the mistake easy. Filing-text extraction says modern EDGAR
filings embed an `<ix:header>` that browsers do not display and that
BeautifulSoup's `get_text` does not skip, and it strips that element plus
nodes whose style contains `display:none`
(`filing_text_projection.py:136-153`). Auditor extraction looks for
`auditorname`, `auditorfirmid`, and `auditorlocation` on tags in that same
HTML parse (`auditor_evidence.py:105-127`). Those tags sit in an HTML
document. An XML pull parser rejects the unclosed tags, omitted quotes,
and HTML-only constructions that the HTML parser is required to accept.
lol_html would be the Rust tool whose own docs match a "walk the HTML and
drop some nodes" job. It still would not decide which compensation table
is the Summary Compensation Table.

The source-contract HTML demo uses `html.parser.HTMLParser`
(`html-demo/custom.py:8-36`) on a fixture with one regular table
(`html-demo/contract.yaml:22-28`). The spec already records that this did
not run on a real DEF 14A (`spec.md:1061-1062`).

## Where the work sits, family by family

**Forms 3/4/5.** The bytes are small per filing and the XML shape is
fixed. The prototype already decodes them by configuration, including the
`<XML>` envelope, footnote markers, and the "see remarks" title rewrite
(`form345/contract.yaml:9-16`, `form345/contract.yaml:31-34`). What is
left in Python is edgartools: `reverse_name` and `_classify_is_individual`
over bronze submissions (`ownership.py:41-48`, `form345/custom.py:15-30`).
A Rust XML reader would reimplement the part the contract already
expresses. It would not remove the edgartools calls unless those two
functions were reimplemented, which is a behavior port, not a parser port.

**13F information table.** The bytes are XML and can be large for one
manager. edgartools already parses them with `lxml.etree`, and that file's
docstring states its own comparison: BeautifulSoup about 10-26 seconds
versus lxml about 1-2 seconds for 24K holdings
(`infotable_xml.py:21-23`). That is edgartools' number, not a measurement
made here, and it compares two Python parsers. This repo's own work after
that call is the pre-Q4-2022 thousands-to-dollars multiplier
(`thirteenf.py:33-35`, `thirteenf.py:158-159`), security classification by
regex (`thirteenf.py:47-66`), and a namespace workaround that rewrites the
document and calls edgartools again (`thirteenf.py:80-112`). The workaround
exists because of how edgartools picks a namespace, not because XML
tokenization is missing.

**13F cover.** One small XML document, a handful of flags, and a closed
vocabulary of amendment types (`thirteenf_cover.py:17-28`). Mechanical,
and too small for a second language to matter.

**Per-filing ADV.** One function accepts XML, HTML, text, and a PDF sniff
(`adv.py:74-84`). Extraction is a list of tag names plus regular
expressions over the whole text (`adv.py:87-106`, `adv.py:148-165`). The
PDF branch does not parse PDF; it still builds a soup. The rules are the
parser. Rust would have to carry the same heuristics.

**ADV bulk, firm roster, PCAOB.** The bytes are CSV, inside a ZIP for the
two SEC/IAPD archives. The csv crate can iterate records. The code that
would remain is the policy: which of hundreds of columns to keep
(`adv_firm_roster_ingest.py:8-10`), three `DateSubmitted` shapes
(`adv_bulk_ingest.py:71-83`), a literal `"N"` that means not reported
(`adv_bulk_ingest.py:90-96`), cp1252 (`adv_bulk_ingest.py:61-66`), and
fail-closed checks. Those are not tokenization.

**Companyfacts.** This is the SEC JSON path that builds one in-memory
object before walking it (`edgartools_sec_gateway.py:212-214`,
`financials.py:79-91`). The walk is mechanical field selection: which
`us-gaap` facts have an accession and a fiscal period in `{FY, Q1, Q2, Q3,
Q4}`, and which `dei` facts become auditor columns
(`financials.py:36-48`, `financials.py:145-179`). The platform's response
ceiling is 150 MiB (`sec_client.py:23`). That is a cap, not a measured
file size. No companyfacts payload was sized or timed here. Inference:
this is the SEC family where a faster or lower-memory JSON decode could
matter, and only a measurement would say so. The concept maps are not that
decode.

**Submissions, tickers, daily index, reports metadata.** JSON objects or
text lines, decoded and then projected into columns. `is_individual_filer`
is a domain rule over `entityType`, recent forms, SIC, and tickers, and
the comment records why `entityType == "other"` is not enough
(`bronze_submission_extractors.py:38-62`). The daily index is one
anchored regex per line (`bronze_daily_index_extractors.py:29-34`). These
are repeated, but each artifact is one company or one day, and the work
after the decode is field policy.

**GLEIF.** The production reader does not load the archive into one tree.
It feeds 64 KiB chunks to an lxml pull parser or to `ijson`, and it refuses
a compressed member above 1 GiB, an expanded member above 16 GiB, or a
record above 1 MiB (`gleif_source.py:91-98`, `gleif_source.py:167-177`,
`gleif_source.py:243-245`). The prototype's JSONL reader is the small
extract, and the spec says the zip stream was not prototyped
(`spec.md:1063-1064`). Inference: GLEIF is the family whose bytes are
large enough to have forced a streaming design already. Replacing that
stream with quick-xml or a Rust JSON pull parser would be a rewrite of a
parser that already streams, not a fix for a parser that slurps the file.
The record-shape checks around the stream (`gleif_source.py:181-233`) are
the rules.

**DEF 14A.** HTML, not a fixed schema. edgartools selects the Summary
Compensation Table from a pre-parsed `lxml` tree
(`edgar/proxy/html_extractor.py:830-831`). This repo then infers a role
from a title vocabulary (`proxy_fundamentals.py:26-55`) and repairs names
that are really wrapped titles (`proxy_fundamentals.py:59-80`). The spec
keeps this as a hand-written parser (`spec.md:198-208`). A Rust HTML
parser can build the tree. It does not know which table is the
compensation table.

**8-K earnings.** The warehouse comment says the parser delegates scale
detection, statement classification, label normalisation, and period-column
selection to edgartools, and feeds cached HTML so `from_filing` does not
hit the SEC (`earnings_release.py:1-8`, `earnings_release.py:31-36`).
edgartools parses that HTML with a recovering lxml HTML parser
(`edgar/documents/parser.py:177-191`). Guidance extraction is another
heuristic layer (`explore/guidance_facts.py` via
`earnings_release.py:153-170`). The bytes are HTML; the product is a
choice of table and a scale judgment.

**Item 5.02.** The module's own history says regex could not keep up with
real 8-K phrasing, so the extractor is a spaCy dependency parse
(`item_502.py:3-12`). Tag removal is a regex (`item_502.py:165-166`).
The cost that the comments describe is grammatical attachment, including
bullets that are not sentences (`item_502.py:165-176`). A Rust HTML
tokenizer would replace the regex strip and leave the model where it is.

**Filing text, subsidiaries, auditor.** All three are HTML plus a policy
that is the point of the function: drop non-rendered iXBRL
(`filing_text_projection.py:136-153`), find a table whose header says
"subsidiar" and a jurisdiction column (`subsidiary_exhibits.py:75-99`),
or accept one unambiguous auditor triplet and otherwise only a signature
inside a bounded window (`auditor_evidence.py:127-168`). html5ever can
build the tree those policies walk. The policies are not the tree.

**Text signals and external estimates.** `text_extractors.py` states that
it runs on plain text and that edgartools has no equivalent
(`text_extractors.py:1-11`). A search of non-test code found no importer.
Yahoo, Finnhub, and Alpha Vantage are small payloads and field maps. None
of these are a byte-parsing problem.

**Batch XBRL scripts.** `scripts/batch/batch_test_xbrl.py` calls
`filing.xbrl()` (`batch_test_xbrl.py:37-39`). That is edgartools, on a
filing object, outside the warehouse command path. This note did not read
that implementation. It is not evidence that the warehouse parses instance
documents.

## What was not measured

No parser was timed. No artifact size was sampled. The only timing figure
in the sources above is the comment inside edgartools' 13F parser
(`infotable_xml.py:21-23`), and the only size ceilings in this repo that
were read are the 150 MiB SEC response cap (`sec_client.py:23`) and the
GLEIF archive bounds (`gleif_source.py:243-245`). A claim that Rust would
be faster on any of these families is not a result of this research.

## Inference

The families where a Rust parser could do the mechanical job, because a
maintained library matches the bytes, are ownership XML, 13F XML, 13F
cover XML, GLEIF XML, companyfacts and submissions and ticker JSON, GLEIF
JSON, ADV bulk CSV, firm-roster CSV, PCAOB CSV, the daily index as plain
lines, and every HTML family if the library is html5ever, scraper, or
lol_html rather than quick-xml.

The families where that port would buy the thing the code actually spends
its logic on are none of the HTML families, none of the edgartools-backed
families (13F information table, DEF 14A, 8-K earnings), and not Item
5.02. Ownership is already a configuration decode plus two edgartools
calls. Cover XML, ticker JSON, the daily index, and PCAOB CSV are
mechanical and small. ADV bulk and the firm roster are mechanical at the
CSV layer and rule-heavy in the columns. Companyfacts is the SEC parse
that materializes a whole document first; whether that dominates is
unmeasured. GLEIF is the large parse, and it already streams in Python.

A Rust decoder, if one were ever attached, would sit under the current
Python rules and under the current edgartools calls. PyO3 is how that
function would be imported. It is not a reason to move the rules.

This is research only. No implementation was performed.
