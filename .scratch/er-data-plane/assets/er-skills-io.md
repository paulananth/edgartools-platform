# Equity research — 9 skills: inputs & outputs

**Source:** `plugins/vertical-plugins/equity-research/skills/*/SKILL.md`  
**Machine extract:** [er-skills-io.json](./er-skills-io.json)  
**How to re-extract:** see bottom of this file

---

## Quick table

| Skill | Primary inputs | Primary outputs |
|-------|----------------|-----------------|
| **catalyst-calendar** | Universe, sector, horizon, event types | Excel calendar + weekly preview note |
| **earnings-preview** | Company, quarter, consensus, date/time, prior guide | 1-page preview (scenarios + what to watch) |
| **morning-note** | Overnight news/earnings, coverage names, ratings/PTs | ≤1 page morning note (md/Word) |
| **model-update** | Existing model + what changed (actuals/guide/macro) | Updated Excel + estimate/PT change summary |
| **earnings-analysis** | Live release, 10-Q, transcript, consensus+date | 8–12 pp DOCX earnings update + charts |
| **initiating-coverage** | Ticker + filings; then task-chain files | Per-task: md / xlsx / zip / final DOCX |
| **thesis-tracker** | Thesis pillars/risks or new data point | Scorecard + update log (md/Word) |
| **idea-generation** | Screen criteria, universe, long/short, themes | 5–10 idea shortlist + one-pagers |
| **sector-overview** | Sector scope, purpose, depth, universe | Word/PPT landscape + Excel appendix |

---

## 1. catalyst-calendar

### Inputs
| Input | Required? | Notes |
|-------|:---------:|-------|
| List of companies (tickers/names) | Yes | Coverage universe |
| Sector / industry focus | Yes | |
| Include macro events? | Ask | Fed, CPI, GDP, etc. |
| Time horizon | Yes | 2 weeks / month / quarter |
| Per-company catalysts | Gather | Earnings date/time, AGM, investor day, product, FDA, M&A milestones, conferences, etc. |

### Outputs
| Output | Format |
|--------|--------|
| Calendar workbook | Excel — sortable columns: Date, Event, Company, Type, Impact (H/M/L), Positioning, Notes |
| Weekly preview | Markdown email/note — this week, next week, position implications |
| Optional | Google Calendar integration (aspirational) |

---

## 2. earnings-preview

### Inputs
| Input | Required? | Notes |
|-------|:---------:|-------|
| Company | Yes | |
| Reporting quarter | Yes | e.g. Q3 FY25 |
| Consensus estimates | Yes | Rev, EPS, key segments — with source |
| Earnings date & time | Yes | Pre-market vs after-hours |
| Prior quarter guide / call | Recommended | What mgmt teed up |
| Sector-specific ops metrics | As needed | ARR, SSS, backlog, NIM, etc. |
| Recent stock / options context | Recommended | For trading setup / implied move |

### Outputs
| Output | Format |
|--------|--------|
| Earnings preview | **One page**: company/quarter/date; consensus table; ranked metrics to watch; bull/base/bear scenarios; catalyst checklist; trading setup |

---

## 3. morning-note

### Inputs
| Input | Required? | Notes |
|-------|:---------:|-------|
| Coverage universe / sector | Yes | What names you own on the desk |
| Overnight / pre-market news | Yes | Earnings, M&A, mgmt, ratings, macro |
| If earnings print: consensus vs actual | When relevant | Rev, EPS, key metric, guidance |
| Current ratings / price targets | Recommended | For reiterate/change language |
| Today’s calendar | Recommended | Calls, data releases, conferences |

### Outputs
| Output | Format |
|--------|--------|
| Morning note | **Markdown** (email/Slack) or short Word — max **1 page** |
| Structure | Top call; overnight bullets; key events today; optional trade ideas; optional quick earnings table + take |

---

## 4. model-update

### Inputs
| Input | Required? | Notes |
|-------|:---------:|-------|
| **Existing financial model** | Yes | File path / workbook |
| Update trigger type | Yes | Earnings / guidance / estimate revision / macro / event |
| Reported actuals (if earnings) | When earnings | Rev, GM, opex, EBITDA, EPS, segments, cash, debt, shares, capex, WC |
| New guidance or assumption changes | When relevant | Growth, margins, one-offs |
| Macro drivers | When relevant | Rates, FX, commodities |

### Outputs
| Output | Format |
|--------|--------|
| Updated model | Excel (if user provided model) |
| Estimate change summary | Markdown or Word — old vs new FY / next FY |
| Valuation / PT update | Table: DCF, P/E, EV/EBITDA, **price target** |
| Action summary | Thesis-changing vs noise; maintain/upgrade/downgrade |

---

## 5. earnings-analysis

### Inputs
| Input | Required? | Notes |
|-------|:---------:|-------|
| Company + quarter/year | Yes | Already under coverage |
| **Live** earnings materials | Yes | Release, 10-Q, transcript, IR deck — **not training data** |
| Consensus + **as-of date** | Yes | Bloomberg/FactSet/etc. |
| Prior guidance | Yes | For guide-vs-guide |
| Today’s date / release date check | Yes | Freshness protocol (within ~3 months) |
| Existing model | Optional | For estimate/PT update |

### Outputs
| Output | Format |
|--------|--------|
| Earnings update report | **DOCX** 8–12 pp, 3–5k words |
| File name | `[Company]_Q[Quarter]_[Year]_Earnings_Update.docx` |
| Contents | Summary + rating/PT; results; metrics/guidance; thesis; valuation/estimates; optional appendix |
| Charts | 8–12 embedded |
| Tables | 1–3 summary only |
| Sources | Clickable hyperlinks + sources section |
| Optional | XLS model update |

---

## 6. initiating-coverage (5 tasks)

### Inputs by task

| Task | Inputs required |
|------|-----------------|
| **1 Research** | Company name/ticker only |
| **2 Model** | 10-K / financials **or** user hist IS/BS/CF (3–5y); optional Task 1 for context |
| **3 Valuation** | **Task 2 model** (projections, DCF inputs) — hard stop if missing |
| **4 Charts** | Task 1 research + Task 2/3 model + external prices/multiples |
| **5 Report** | **All** of: research `.md`, model `.xlsx`, valuation `.md`, charts `.zip` |

### Outputs by task

| Task | Deliverable(s) only |
|------|---------------------|
| **1** | `[Company]_Research_Document_[Date].md` (6–8k words) |
| **2** | `[Company]_Financial_Model_[Date].xlsx` (6 essential tabs); optional hist extract xlsx |
| **3** | `[Company]_Valuation_Analysis_[Date].md` + **tabs added to Task 2 xlsx** (DCF, sensitivity, comps, summary) |
| **4** | `[Company]_Charts_[Date].zip` (25–35 PNG/JPG @ 300 DPI + chart_index.txt) |
| **5** | `[Company]_Initiation_Report_[Date].docx` (30–50 pp, 10k+ words, 25+ charts, 12+ tables) |

**Do not create** extra “completion summaries” or side docs per task.

---

## 7. thesis-tracker

### Inputs
| Input | Required? | Notes |
|-------|:---------:|-------|
| Company + ticker | Yes | |
| Long or short | Yes | |
| Thesis statement (1–2 sentences) | Yes if new | |
| Key pillars (3–5) | Yes if new | |
| Key risks / invalidators (3–5) | Yes if new | |
| Catalysts | Recommended | |
| Target price / valuation | Recommended | |
| Stop / exit trigger | Recommended | |
| **New data point** | Yes if update | Date, what changed, pillar impact |

### Outputs
| Output | Format |
|--------|--------|
| Thesis summary | Markdown or Word |
| Update log | Date / data point / impact / action / conviction |
| Scorecard table | Pillar vs original vs current vs trend |
| Mini catalyst table | Upcoming events |
| Use cases | Morning meeting, portfolio review, risk committee |

---

## 8. idea-generation

### Inputs
| Input | Required? | Notes |
|-------|:---------:|-------|
| Search criteria / screen type | Yes | Quant screens, shorts, special sits, thematic |
| Universe definition | Yes | Sector, market cap, geography, etc. |
| Long vs short bias | Yes | |
| Theme (if thematic) | When thematic | e.g. AI infrastructure |
| Factor thresholds | When screening | Skill lists example metrics (yield, growth, etc.) |

### Outputs
| Output | Format |
|--------|--------|
| Idea shortlist | **5–10** ideas |
| Per-idea card | One-line thesis; metrics vs peers; mispricing; catalyst; falsifier; next step (model/DD/call) |
| Optional | Queue for full model / initiation |

---

## 9. sector-overview

### Inputs
| Input | Required? | Notes |
|-------|:---------:|-------|
| Sector / subsector definition | Yes | How narrow |
| Purpose | Yes | Client / internal / pitch / ideas |
| Depth | Yes | ~5–10 pp vs ~20–30 pp |
| Angle | Yes | Neutral landscape vs thematic thesis |
| Universe | Yes | Public only vs include private |
| Market size, peers, multiples, trends | Gather | From filings, industry sources, market data |

### Outputs
| Output | Format |
|--------|--------|
| Sector report | **Word or PowerPoint** |
| Contents | Market overview; competitive map; company comparison table; valuation context; investment implications |
| Appendix | **Excel** with detailed company data |
| Charts | Market growth, share, valuation history |

---

## How to extract this yourself

### Option A — one-shot script (from repo root)

```bash
cd /Users/aneenaananth/projects/financial-services

python3 << 'PY'
import re, json, pathlib

ROOT = pathlib.Path("plugins/vertical-plugins/equity-research/skills")
out = []

for skill_dir in sorted(ROOT.iterdir()):
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        continue
    text = skill_md.read_text(encoding="utf-8")
    body = text.split("---", 2)[-1] if text.startswith("---") else text

    # Grab Step / Phase / Output headings + following bullets
    sections = re.split(r"(?=^#{1,3}\s+)", body, flags=re.M)
    rec = {"skill": skill_dir.name, "inputs": [], "outputs": []}
    for sec in sections:
        first = sec.splitlines()[0] if sec.strip() else ""
        title = re.sub(r"^#+\s*", "", first).strip()
        bullets = re.findall(r"^[-*]\s+(.+)$", sec, re.M)
        if re.search(r"input|gather|step 1|require|define|context|data collection|prereq", title, re.I):
            rec["inputs"].append({"section": title, "bullets": bullets})
        if re.search(r"output|deliverable|specification", title, re.I):
            rec["outputs"].append({"section": title, "bullets": bullets})
        # filename patterns
    rec["files"] = re.findall(r"`(\[[^\]]+\][^`]*\.(?:xlsx|docx|md|zip))`", body)
    out.append(rec)

pathlib.Path(".scratch/skill-quality-review/er-skills-io.json").write_text(
    json.dumps(out, indent=2)
)
print(json.dumps(out, indent=2))
PY
```

### Option B — ripgrep by heading

```bash
# List Output / Step 1 sections across all 9 skills
rg -n "^## (Step 1|.*Output|Critical Requirements|Phase 1)" \
  plugins/vertical-plugins/equity-research/skills/*/SKILL.md
```

### Option C — open each skill

```bash
ls plugins/vertical-plugins/equity-research/skills/
# open plugins/vertical-plugins/equity-research/skills/<name>/SKILL.md
```

Look for: **Step 1** (inputs), **Step N: Output** / **Output Specification** (outputs), and for initiation the **Task** tables.

### Option D — use the saved inventory

| File | Content |
|------|---------|
| [er-skills-io.md](./er-skills-io.md) | This curated inputs/outputs list |
| [er-skills-io.json](./er-skills-io.json) | Raw section extract from script |
| [SKILL-IO.md](./SKILL-IO.md) | All 66 skills (broader) |

---

## Agent copies

The same 9 skills are **copied** into agents (e.g. `earnings-reviewer` has a subset). **Edit only** under `vertical-plugins/equity-research/skills/`, then:

```bash
python3 scripts/sync-agent-skills.py
```

I/O does not change between vertical source and agent copy.
