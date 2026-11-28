"""Read-only browser preview of the hosted-store clear workflow."""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit
from pathlib import Path

from .hosted_store_clear_progress import ProgressError, STEPS, snapshot as progress_snapshot




def page(run_id: str | None = None, stores_folder=None) -> str:
    run = progress_snapshot(run_id, stores_folder) if run_id else None
    step_rows = []
    for index, step in enumerate(STEPS, 1):
        current = run["steps"][step["id"]] if run else {
            "state": "not_started", "completed": 0, "total": step["total"], "unit": step["unit"],
        }
        state = current["state"]
        state_label = {
            "not_started": "Not started",
            "running": "Running",
            "complete": "Complete",
            "failed": "Failed",
        }[state]
        step_rows.append(
            f'<li class="step"><div class="step-head"><span class="number">{index}</span>'
            f'<div class="step-copy"><h2>{step["title"]}</h2><p>{step["description"]}</p></div>'
            f'<span id="state-{step["id"]}" class="state" data-state="{state}">{state_label}</span></div>'
            f'<div class="progress-label"><span>Verified work</span>'
            f'<span id="count-{step["id"]}">{current["completed"]} / {current["total"]} {current["unit"]}</span></div>'
            f'<progress id="progress-{step["id"]}" max="{current["total"]}" value="{current["completed"]}" '
            f'aria-label="{step["title"]}: {current["completed"]} of {current["total"]} {current["unit"]}">'
            f'{current["completed"]}</progress></li>'
        )
    preview = run is None
    badge = "Preview only · not running" if preview else f"Run {run_id[:8]} · read-only monitor"
    notice_title = "No cleanup has started." if preview else "Monitor only. This page cannot start cleanup."
    notice_text = (
        "Bars show example work units at zero, not live progress."
        if preview else "Progress updates come from this run's verified step events; no cleanup action is available here."
    )
    run_state = "Preview" if preview else run["state"].replace("_", " ").title()
    live_script = "" if preview else """
    <script>
      (() => {
        const steps = ["preflight","backups","reset","rdm","archive","readiness"];
        const live = document.getElementById("live-state");
        let lastAnnouncement = "";
        async function refresh() {
          try {
            const response = await fetch("/progress", {cache:"no-store"});
            if (!response.ok) throw new Error("status unavailable");
            const run = await response.json();
            for (const id of steps) {
              const item = run.steps[id];
              const bar = document.getElementById(`progress-${id}`);
              const count = document.getElementById(`count-${id}`);
              const state = document.getElementById(`state-${id}`);
              bar.max = item.total;
              bar.value = item.completed;
              bar.setAttribute("aria-label", `${item.title}: ${item.completed} of ${item.total} ${item.unit}`);
              count.textContent = `${item.completed} / ${item.total} ${item.unit}`;
              state.dataset.state = item.state;
              state.textContent = ({not_started:"Not started",running:"Running",complete:"Complete",failed:"Failed"})[item.state];
            }
            const announcement = `Run ${run.state.replaceAll("_"," ")}. Updated ${run.updated_at || "just now"}.`;
            if (announcement !== lastAnnouncement) {
              live.textContent = announcement;
              lastAnnouncement = announcement;
            }
          } catch (_) {
            live.textContent = "Live status is temporarily unavailable. Last verified counts remain shown.";
          }
          window.setTimeout(refresh, 1000);
        }
        refresh();
      })();
    </script>
    """
    safe_run_id = run_id or ""
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Read-only preview of the hosted PostgreSQL store-clear workflow.">
  <meta name="robots" content="noindex">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect x='4' y='4' width='24' height='24' rx='6' fill='%23155eef'/%3E%3Cpath d='M10 16h12M16 10v12' stroke='white' stroke-width='2'/%3E%3C/svg%3E">
  <title>Hosted store clear · Progress</title>
  <style>
    :root {{ color-scheme: light dark; --page:#f4f6f8; --surface:#fff; --ink:#182230; --muted:#536273; --line:#d7dee7; --accent:#155eef; --good:#067647; --warning:#b54708; --bad:#b42318; }}
    @media (prefers-color-scheme:dark) {{ :root {{ --page:#121820; --surface:#1b2530; --ink:#f0f4f8; --muted:#b7c2cf; --line:#344353; --accent:#84adff; --good:#75e0a7; --warning:#fdb022; --bad:#fda29b; }} }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--page); color:var(--ink); font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    .skip {{ position:absolute; left:-10000px; top:8px; }} .skip:focus {{ left:8px; z-index:2; padding:8px 12px; background:var(--surface); color:var(--ink); }}
    main {{ max-width:1100px; margin:0 auto; padding:28px 24px 48px; }}
    header {{ display:flex; align-items:flex-start; justify-content:space-between; gap:20px; border-bottom:1px solid var(--line); padding-bottom:18px; }}
    .eyebrow {{ margin:0 0 8px; color:var(--muted); font-size:12px; font-weight:700; letter-spacing:.08em; }}
    h1 {{ margin:0; font-size:clamp(24px,4vw,32px); line-height:1.2; text-wrap:balance; }}
    .subtitle {{ margin:8px 0 0; color:var(--muted); }}
    .badge {{ flex:none; border:1px solid var(--warning); border-radius:999px; padding:6px 12px; color:var(--warning); font-size:12px; font-weight:700; }}
    .notice {{ margin:18px 0; padding:12px 16px; border:1px solid var(--warning); border-radius:9px; background:var(--surface); }}
    .notice strong {{ display:block; font-size:14px; }} .notice p {{ margin:3px 0 0; color:var(--muted); font-size:13px; }}
    .panel {{ margin-top:16px; padding:18px 20px; border:1px solid var(--line); border-radius:10px; background:var(--surface); }}
    .panel-title {{ margin:0 0 14px; font-size:15px; }}
    .target {{ display:flex; align-items:center; justify-content:space-between; gap:16px; }}
    .label {{ display:block; color:var(--muted); font-size:11px; font-weight:700; letter-spacing:.07em; }}
    .target strong {{ display:block; margin-top:4px; font:600 16px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; }}
    .scope {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
    .scope p {{ margin:6px 0 0; font-size:13px; }}
    .muted {{ color:var(--muted); }}
    .scope-note {{ margin:14px 0 0; font-size:12px; }}
    .steps {{ display:grid; gap:10px; margin:0; padding:0; list-style:none; }}
    .step {{ padding:14px 16px 12px; border:1px solid var(--line); border-radius:9px; background:var(--surface); }}
    .step-head {{ display:grid; grid-template-columns:32px minmax(0,1fr) auto; align-items:start; gap:12px; }}
    .number {{ display:grid; place-items:center; width:28px; height:28px; border:1px solid var(--line); border-radius:50%; color:var(--muted); font-size:12px; font-weight:700; }}
    .step h2 {{ margin:0; font-size:14px; }} .step p {{ margin:3px 0 0; color:var(--muted); font-size:12px; }}
    .state {{ padding:3px 8px; border:1px solid var(--line); border-radius:999px; color:var(--muted); font-size:11px; white-space:nowrap; }}
    .state[data-state=running] {{ border-color:var(--accent); color:var(--accent); }}
    .state[data-state=complete] {{ border-color:var(--good); color:var(--good); }}
    .state[data-state=failed] {{ border-color:var(--bad); color:var(--bad); }}
    .progress-label {{ display:flex; justify-content:space-between; gap:12px; margin:10px 0 4px 44px; color:var(--muted); font-size:11px; }}
    progress {{ display:block; width:calc(100% - 44px); height:8px; margin-left:44px; border:0; border-radius:999px; overflow:hidden; appearance:none; }}
    progress::-webkit-progress-bar {{ background:var(--line); border-radius:999px; }} progress::-webkit-progress-value {{ background:var(--accent); border-radius:999px; }} progress::-moz-progress-bar {{ background:var(--accent); border-radius:999px; }}
    footer {{ margin-top:16px; padding:14px 16px; border:1px solid var(--line); border-radius:9px; color:var(--muted); background:var(--surface); font-size:12px; }}
    @media(max-width:680px) {{ main {{ padding:20px 14px 32px; }} header {{ flex-direction:column; }} .target {{ align-items:flex-start; flex-direction:column; }} .target .state {{ white-space:normal; }} .scope {{ grid-template-columns:1fr; gap:14px; }} .step-head {{ grid-template-columns:28px minmax(0,1fr); }} .state {{ grid-column:2; justify-self:start; }} .progress-label,progress {{ margin-left:40px; }} progress {{ width:calc(100% - 40px); }} }}
    @media(prefers-reduced-motion:reduce) {{ *,*::before,*::after {{ scroll-behavior:auto !important; animation-duration:.01ms !important; transition-duration:.01ms !important; }} }}
  </style>
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <main id="main" data-run-id="{safe_run_id}">
    <header>
      <div><p class="eyebrow">EDGARTOOLS / DATA OPERATIONS</p><h1>Clear hosted stores for a fresh load</h1><p class="subtitle">Review ordered steps and their verified work counters.</p></div>
      <span class="badge">{badge}</span>
    </header>
    <aside class="notice" aria-label="Progress safety notice">
      <strong>{notice_title}</strong>
      <p>{notice_text}</p>
    </aside>
    <p id="live-state" class="muted" role="status" aria-live="polite" aria-atomic="true">{run_state} progress.</p>
    <section class="panel" aria-labelledby="target-title">
      <h2 class="panel-title" id="target-title">Target</h2>
      <div class="target"><div><span class="label">HOSTED POSTGRES INSTANCE</span><strong>EDGARTOOLS_PROD_MDM</strong></div><span class="state">Production · scope from prior plan</span></div>
    </section>
    <section class="panel" aria-labelledby="scope-title">
      <h2 class="panel-title" id="scope-title">Scope boundary</h2>
      <div class="scope">
        <div><span class="label">CLEAR TABLE DATA IN FIVE STORES</span><p>MDM · RDM · Silver · Bookkeeping · Change Journal</p></div>
        <div><span class="label">PRESERVE</span><p>Rules config · instance and databases · schemas · roles and logins · captured source files</p></div>
      </div>
      <p class="muted scope-note">This is a table reset, not an instance or database drop. Recheck mirror state before any future run; a live mirror needs its own suspend, restart and read-back gates.</p>
    </section>
    <section class="panel" aria-labelledby="steps-title">
      <h2 class="panel-title" id="steps-title">Ordered steps · verified counters</h2>
      <ol class="steps">{''.join(step_rows)}</ol>
    </section>
    <footer>Progress comes from run-scoped step events. This page is read-only; cleanup commands require their separate manifests, digests and approval words. No cleanup run has been started by this preview.</footer>
  </main>
  {live_script}
</body>
</html>
'''


class _PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self._respond(200, "text/html; charset=utf-8", page(self.server.run_id, self.server.stores_folder).encode("utf-8"))
            return
        if path == "/progress" and self.server.run_id:
            try:
                current = progress_snapshot(self.server.run_id, self.server.stores_folder)
            except (FileNotFoundError, ProgressError):
                self._respond(404, "application/json; charset=utf-8", b"{\"error\":\"Progress run not found.\"}\n")
                return
            for step in current["steps"].values():
                step.pop("units", None)
            body = json.dumps(current, ensure_ascii=True, allow_nan=False).encode("utf-8")
            self._respond(200, "application/json; charset=utf-8", body)
            return
        self._respond(404, "text/plain; charset=utf-8", b"Not found\n")

    def do_POST(self):
        self._respond(405, "text/plain; charset=utf-8", b"Read-only monitor; no cleanup actions are available.\n")

    def _respond(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "form-action 'none'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def create_server(port: int = 0, run_id: str | None = None, stores_folder=None) -> HTTPServer:
    """Create a loopback-only read-only preview or progress monitor."""
    if not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535.")
    if run_id:
        progress_snapshot(run_id, stores_folder)
    server = HTTPServer(("127.0.0.1", port), _PreviewHandler)
    server.run_id = run_id
    server.stores_folder = stores_folder
    return server


def serve(args) -> int:
    """Open a local preview or monitor a run ID; exposes no cleanup endpoint."""
    server = create_server(args.port, args.run_id, args.stores_folder)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Read-only hosted-store progress: {url}. Press Ctrl+C to stop.", flush=True)
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
        "hosted-store-clear-preview",
        help="Open the read-only hosted-store clear progress preview",
    )
    command.add_argument("--port", type=int, default=0, help="Loopback server port (default: choose an available port)")
    command.add_argument("--run-id", help="Show live events from an existing progress run")
    command.add_argument("--stores-folder", type=Path, help="Progress journal directory (defaults to STORES_FOLDER)")
    command.set_defaults(handler=serve)


