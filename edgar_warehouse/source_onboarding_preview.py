"""Read-only visual guide to the repository's source-onboarding sequence."""

from __future__ import annotations

import html
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit


WHOLE_SOURCE_STEPS = (
    (
        "Discover",
        "Profile the retained data set once, using existing repository knowledge and approved findings where available.",
        "Approved findings.yaml for these capture files. It records parts, keys, relationships, time roles, code lists, sensitivity, and measured quality findings.",
    ),
    (
        "Plan parts",
        "Order the work from the approved findings before identifying a part.",
        "An operator-reviewed list: MDM master parts first, then RDM reference parts, then silver transaction parts and separate relationships. Metadata-only parts go to Bookkeeping.",
    ),
)

PART_STEPS = (
    (
        "Identify",
        "Name the provider, data set, source codes, and capture family; check whether this is genuinely new onboarding.",
        "A source entry in the onboarding log. If the source already has rules and the change edits its mapping, stop and use Refining Rules instead.",
    ),
    (
        "Profile",
        "Use the approved findings for this part; do not profile the same unchanged captures again.",
        "The part's record key, identifier proposals, columns, relationships, code lists, time roles, and quality findings are understood.",
    ),
    (
        "Map",
        "Apply approved modeling decisions to the source contract, target, and source sequence.",
        "Reviewed source.yaml and any required kind rules. Master fields stay in MDM; silver contains transaction facts and link keys.",
    ),
    (
        "Quality",
        "Turn measured findings into checks and fixes with Data Quality; defects block rather than being waived.",
        "Approved dispositions and fixes, with sources/<source>/quality.yaml passing rules check.",
    ),
    (
        "Metadata",
        "Prepare the Mapping Document and technical catalog metadata from the reviewed configuration.",
        "An agreed MAPPING.xlsx that passes mapdoc check. Silver parts also publish the approved public summary to profile.yaml.",
    ),
    (
        "Check",
        "Validate the source configuration and run the owner-specific tests for changed readers.",
        "rules check --source <source>, mapdoc check, and the scoped tests pass. These checks do not prove a load.",
    ),
    (
        "Load handoff",
        "Hand the agreed configuration, retained captures, and approvals to Data Operations for the initial local proof and load.",
        "Data Operations owns connection readiness and the load. This guide never submits a run or reports data as loaded.",
    ),
)

PART_ORDER = (
    ("01", "Master", "MDM first; keep relationships marked onboard: together with their master."),
    ("02", "Reference", "RDM code sets next; use them where a value's meaning depends on a published code."),
    ("03", "Transaction", "Silver last; include relationships marked separate. Metadata-only parts route to Bookkeeping."),
)


def _step(group: str, number: str, title: str, summary: str, evidence: str) -> str:
    return f'''<li class="stage">
      <span class="stage-number" aria-hidden="true">{number}</span>
      <div class="stage-body">
        <h3>{title}</h3>
        <p>{summary}</p>
        <details name="{group}"><summary>Show completion evidence</summary><p>{evidence}</p></details>
      </div>
    </li>'''


def page(source_name: str | None = None) -> str:
    """Render a static workflow map; it reads no source or run state."""
    source = html.escape(source_name.strip() if source_name and source_name.strip() else "New source", quote=True)
    whole_source = "\n".join(
        _step("whole-source", f"0{index}", title, summary, evidence)
        for index, (title, summary, evidence) in enumerate(WHOLE_SOURCE_STEPS, 1)
    )
    part_steps = "\n".join(
        _step("part-lifecycle", f"0{index}", title, summary, evidence)
        for index, (title, summary, evidence) in enumerate(PART_STEPS, 1)
    )
    parts = "\n".join(
        f'<li><span class="part-number">{number}</span><div><h3>{title}</h3><p>{description}</p></div></li>'
        for number, title, description in PART_ORDER
    )
    template = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="A read-only step-by-step map for onboarding a new data source.">
  <meta name="robots" content="noindex">
  <title>Source onboarding · Workflow map</title>
  <style>
    :root { color-scheme: light dark; --page:#f4f6f8; --surface:#fff; --ink:#182230; --muted:#536273; --line:#d7dee7; --accent:#155eef; --warning:#b54708; }
    @media (prefers-color-scheme:dark) { :root { --page:#121820; --surface:#1b2530; --ink:#f0f4f8; --muted:#b7c2cf; --line:#344353; --accent:#84adff; --warning:#fdb022; } }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--page); color:var(--ink); font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    main { max-width:1120px; margin:0 auto; padding:28px 24px 48px; }
    .skip { position:absolute; left:-10000px; top:8px; }
    .skip:focus { left:8px; z-index:2; padding:8px 12px; background:var(--surface); color:var(--ink); }
    header { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; border-bottom:1px solid var(--line); padding-bottom:18px; }
    .eyebrow,.label { color:var(--muted); font-size:11px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
    .eyebrow { margin:0 0 8px; }
    h1 { margin:0; font-size:clamp(26px,4vw,36px); line-height:1.15; text-wrap:balance; }
    .subtitle { margin:8px 0 0; color:var(--muted); max-width:68ch; }
    .badge { flex:none; border:1px solid var(--accent); border-radius:999px; padding:6px 12px; color:var(--accent); font-size:12px; font-weight:700; }
    .notice { margin:18px 0; padding:12px 16px; border:1px solid var(--warning); border-radius:9px; background:var(--surface); }
    .notice strong { display:block; font-size:14px; }
    .notice p { margin:3px 0 0; color:var(--muted); font-size:13px; }
    .source-panel,.panel { margin-top:16px; padding:18px 20px; border:1px solid var(--line); border-radius:10px; background:var(--surface); }
    .source-panel { display:flex; align-items:center; justify-content:space-between; gap:16px; }
    .source-panel h2,.panel h2 { margin:0; font-size:15px; }
    .source-name { display:block; margin-top:4px; font:600 18px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; overflow-wrap:anywhere; }
    .section-head { display:flex; align-items:baseline; gap:10px; margin:0 0 14px; }
    .section-index { color:var(--accent); font:700 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace; }
    .flow-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; list-style:none; margin:0; padding:0; }
    .stage { display:grid; grid-template-columns:34px minmax(0,1fr); gap:12px; position:relative; }
    .flow-grid .stage { padding:16px; border:1px solid var(--line); border-radius:9px; background:var(--surface); }
    .stage-number { display:grid; place-items:center; width:30px; height:30px; border:1px solid var(--accent); border-radius:50%; color:var(--accent); font:700 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace; }
    .stage h3 { margin:0; font-size:15px; line-height:1.3; }
    .stage p { margin:5px 0 0; color:var(--muted); font-size:13px; }
    details { margin-top:9px; color:var(--muted); font-size:12px; }
    summary { width:max-content; max-width:100%; color:var(--accent); cursor:pointer; font-weight:650; }
    summary:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
    details p { padding-left:10px; border-left:2px solid var(--line); }
    details[open] { padding-left:10px; border-left:2px solid var(--accent); }
    details[open] summary { color:var(--ink); }
    .disclosure-hint { margin:10px 0 0; color:var(--muted); font-size:12px; }
    .setup { margin-top:14px; padding:12px; border:1px solid var(--line); border-radius:8px; background:var(--page); }
    .part-order { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; list-style:none; margin:0; padding:0; }
    .part-order li { display:grid; grid-template-columns:30px minmax(0,1fr); gap:10px; padding:12px; border:1px solid var(--line); border-radius:8px; background:var(--page); }
    .part-number { display:grid; place-items:center; width:26px; height:26px; border:1px solid var(--line); border-radius:50%; color:var(--muted); font:700 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace; }
    .part-order h3 { margin:1px 0 0; font-size:13px; }
    .part-order p { margin:3px 0 0; color:var(--muted); font-size:12px; }
    .part-flow { list-style:none; margin:0; padding:0; }
    .part-flow .stage { padding:0 0 18px; }
    .part-flow .stage:not(:last-child)::before { content:""; position:absolute; left:14px; top:32px; bottom:-1px; width:1px; background:var(--line); }
    footer { margin-top:16px; padding:14px 16px; border:1px solid var(--line); border-radius:9px; color:var(--muted); background:var(--surface); font-size:12px; }
    @media(max-width:720px) { main { padding:20px 14px 32px; } header,.source-panel { align-items:flex-start; flex-direction:column; } .flow-grid,.part-order { grid-template-columns:1fr; } .source-panel .badge { white-space:normal; } }
    @media(prefers-reduced-motion:reduce) { *,*::before,*::after { scroll-behavior:auto !important; animation-duration:.01ms !important; transition-duration:.01ms !important; } }
  </style>
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <main id="main">
    <header>
      <div><p class="eyebrow">EDGARTOOLS / DATA ONBOARDING</p><h1>Onboard a source, one evidence-backed step at a time</h1><p class="subtitle">A workflow map for a new source or domain. Discover and plan the whole data set, then repeat the part lifecycle in dependency order.</p></div>
      <span class="badge">Guide only · no run state</span>
    </header>
    <aside class="notice" aria-label="Read-only guide notice"><strong>This page is a map, not a source inspection or progress report.</strong><p>It reads no captures, configuration, database, or credentials; it starts no profile, check, or load. Each completion gate names evidence to review.</p></aside>
    <p class="disclosure-hint">Open a step to reveal its completion evidence. Each sequence keeps only one detail expanded.</p>
    <section class="source-panel" aria-labelledby="source-title"><div><span class="label">SOURCE IN VIEW</span><h2 class="source-name" id="source-title">__SOURCE__</h2></div><span class="badge">New source / new domain</span></section>
    <section class="panel" aria-labelledby="whole-title"><div class="section-head"><span class="section-index">01—02</span><h2 id="whole-title">Whole data set · before any part</h2></div><ol class="flow-grid">__WHOLE_SOURCE_STEPS__</ol></section>
    <section class="panel" aria-labelledby="order-title"><div class="section-head"><span class="section-index">PLAN OUTPUT</span><h2 id="order-title">Parts are handled in dependency order</h2></div><ol class="part-order">__PART_ORDER__</ol><details name="rules-setup" class="setup"><summary>Rules Database setup (only if missing)</summary><p>If the Rules Database is missing, provision its database, roles, and owner connection, then run <code>edgar-warehouse rules init</code> before Identify. Schema changes use the same command again.</p></details></section>
    <section class="panel" aria-labelledby="part-title"><div class="section-head"><span class="section-index">REPEAT PER PART</span><h2 id="part-title">Seven steps · reveal each completion gate</h2></div><ol class="part-flow">__PART_STEPS__</ol></section>
    <footer>New source or domain only. Changes to an already configured source's mapping belong to Refining Rules. Open this guide with <code>edgar-warehouse source-onboarding-guide --source &lt;source&gt;</code>.</footer>
  </main>
</body>
</html>
'''
    return (
        template.replace("__SOURCE__", source)
        .replace("__WHOLE_SOURCE_STEPS__", whole_source)
        .replace("__PART_ORDER__", parts)
        .replace("__PART_STEPS__", part_steps)
    )


class _GuideHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path != "/":
            self._respond(404, "text/plain; charset=utf-8", b"Not found\n")
            return
        self._respond(200, "text/html; charset=utf-8", page(self.server.source_name).encode("utf-8"))

    def do_POST(self):
        self._respond(405, "text/plain; charset=utf-8", b"Read-only guide; no onboarding actions are available.\n")

    def _respond(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; "
            "form-action 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def create_server(port: int = 0, source_name: str | None = None) -> HTTPServer:
    """Create a loopback-only, read-only onboarding workflow guide."""
    if not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535.")
    server = HTTPServer(("127.0.0.1", port), _GuideHandler)
    server.source_name = source_name
    return server


def serve(args) -> int:
    """Open the read-only onboarding guide on loopback."""
    server = create_server(args.port, args.source)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Read-only source onboarding guide: {url}. Press Ctrl+C to stop.", flush=True)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def register(subparsers):
    command = subparsers.add_parser(
        "source-onboarding-guide",
        help="Open the read-only step-by-step source onboarding guide",
    )
    command.add_argument("--source", help="Source name shown in the guide")
    command.add_argument("--port", type=int, default=0, help="Loopback server port (default: choose an available port)")
    command.set_defaults(handler=serve)
