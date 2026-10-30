"""Generate the review page from the same invented configuration as the API pilot."""
import html
import json
from pathlib import Path


def render(config, receipt):
    escape = html.escape
    datasets = config['datasets']
    width = max(960, len(datasets) * 300)
    pitch = width / len(datasets)
    svg = [f'<svg viewBox="0 0 {width} 350" role="img" aria-label="Data flow above separate control lanes">',
           '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="currentColor"/></marker></defs>']
    positions = {dataset['name']: index * pitch + 20 for index, dataset in enumerate(datasets)}
    for step in config['stages']:
        x, target = positions[step['input']] + 210, positions[step['output']]
        svg.append(f'<g id="edge-{escape(step["name"])}"><title>{escape(step["description"])}</title><path d="M{x} 72 H{target-10}" stroke="currentColor" fill="none" marker-end="url(#arrow)"/><text x="{(x+target)/2}" y="35" text-anchor="middle" font-size="15">{escape(step["title"])}</text></g>')
    for dataset in datasets:
        x = positions[dataset['name']]
        svg.append(f'<g id="dataset-{escape(dataset["name"])}"><title>{escape(dataset["description"])}</title><rect x="{x}" y="48" width="210" height="55" rx="12" fill="var(--node)" stroke="currentColor"/><text x="{x+105}" y="81" text-anchor="middle" font-size="17">{escape(dataset["title"])}</text></g>')
    for index, control in enumerate(config['controls']):
        y = 170 + index * 95
        svg.append(f'<g id="lane-{escape(control["name"])}"><title>{escape(control["description"])}</title><rect x="20" y="{y}" width="{width-40}" height="55" rx="12" fill="var(--lane)"/><text x="38" y="{y+33}" font-size="18">{escape(control["title"])}</text>')
        for relation in control['interactions']:
            step = next(item for item in config['stages'] if item['name'] == relation['stage'])
            x = (positions[step['input']] + 210 + positions[step['output']]) / 2
            svg.append(f'<g id="interaction-{escape(control["name"])}-{escape(step["name"])}"><title>{escape(relation["description"])}</title><path d="M{x} {y} V110" stroke="currentColor" stroke-dasharray="4 6" opacity=".4"/><text x="{x+28}" y="{y+33}" font-size="14">{escape(relation["label"])}</text></g>')
        svg.append('</g>')
    svg.append('</svg>')
    stages = []
    for step in config['stages']:
        mappings = ''.join(f'<li><code>{escape(", ".join(mapping["from"]))}</code> → <code>{escape(mapping["to"])}</code><p>{escape(mapping["transformation"])}</p></li>' for mapping in step['mappings'])
        checks = ''.join(f'<li>{escape(check["rule"])}: <code>{escape(check["field"])}</code>; failure action: {escape(check["failure_action"])}</li>' for check in step['checks']) or '<li>No quality check declared for this example stage.</li>'
        stages.append(f'<details class="card" id="stage-{escape(step["name"])}"><summary>{escape(step["title"])}</summary><p>{escape(step["description"])}</p><h3>Field mappings</h3><ul>{mappings}</ul><h3>Quality checks</h3><ul>{checks}</ul><p>Prerequisites: {escape(", ".join(step["requires"]) or "none")}</p><p class="muted">Configured operation: <code>{escape(step["operation"])}</code></p></details>')
    controls = ''.join(f'<details class="card"><summary>{escape(control["title"])} interactions</summary><p>{escape(control["description"])}</p><ul>' + ''.join(f'<li><strong>{escape(item["stage"])}</strong>: {escape(item["description"])}</li>' for item in control['interactions']) + f'</ul><p class="muted">Implementation reference: <code>{escape(control["reference"])}</code></p></details>' for control in config['controls'])
    native = 'http://localhost:8585/table/' + config['namespace'] + '.example.flow.published/lineage'
    overview = ''.join(f'<p><strong>{escape(control["title"])}</strong> — {escape(control["description"])}</p>' for control in config['controls'])
    return '''<!doctype html><html lang="en" data-theme="light"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>One pipeline · lineage review</title>
<link href="https://cdn.jsdelivr.net/npm/daisyui@5/dist/full.css" rel="stylesheet"><script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
<style>:root{--node:#e7f0ff;--lane:#ecf2ee}body{background:#f5f7fb;color:#203047;font:17px/1.6 system-ui;margin:0}main{max-width:1100px;margin:auto;padding:32px 20px}h1{font-size:clamp(28px,5vw,44px);font-weight:750;line-height:1.15}h2{font-size:25px;font-weight:700;margin:15px 0}h3{font-weight:700;margin-top:18px}.card{display:block;background:white;border:1px solid #d9e2ec;border-radius:16px;padding:22px;margin:20px 0;min-width:0;overflow-wrap:anywhere}.muted{color:#53667e;font-size:14px}summary{cursor:pointer;font-size:20px;font-weight:650}p{margin:12px 0}ul{padding-left:25px;list-style:disc}code{overflow-wrap:anywhere;font-size:14px}svg{width:100%;height:auto;display:block}button,a.btn{margin:8px 8px 8px 0}a{color:#234db8;text-decoration:underline}.badge{white-space:normal;height:auto;padding:6px 12px}.proof{border-left:4px solid #2a8162;padding-left:18px}html[data-theme=dark] body{background:#111c2b;color:#e6edf6}html[data-theme=dark] .card{background:#1c2b3d;border-color:#34475b}html[data-theme=dark]{--node:#263c59;--lane:#233b34}html[data-theme=dark] .muted{color:#bccbdc}html[data-theme=dark] a{color:#a5c2ff}</style>
<main><div class="badge badge-outline">Invented metadata · one-pipeline pilot</div><button class="btn btn-sm" onclick="document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'">Light / dark</button>
<h1>See the flow. Open the detail when needed.</h1><p>This is one isolated example for review, not the platform-wide rollout.</p>''' + '<section class="card"><h2>Avoid doing the same work twice</h2>' + overview + '</section>' + '''
<section class="card proof"><h2>What was tested in OpenMetadata</h2><p>''' + f'{receipt["datasets"]} datasets · {receipt["stages"]} stages · {receipt["field_lineage_edges"]} field lineage links · 1 associated pipeline' + '''</p><p>API readback, incorrect-mapping detection and unchanged repeat pipeline version passed. No execution results were created.</p><p><a href="''' + native + '''" target="_blank" rel="noopener">Open the example’s native catalog lineage ↗</a></p><p class="muted">Native graph and field lineage are API-verified. The lane layout and expandable presentation below are a review preview; they are not an installed OpenMetadata UI feature. No browser-based visual check has been performed.</p></section>
<details class="card" id="pipeline"><summary>Platform overview → ''' + escape(config['title']) + '''</summary><p>One pipeline with two shared control systems. Solid arrows show data movement; dashed lines show control interactions.</p>''' + ''.join(svg) + '''<p class="muted">The pilot contains one pipeline. Cross-pipeline shared-node reuse remains to be implemented and tested.</p><button class="btn btn-outline" onclick="document.querySelectorAll('details').forEach(item=>item.open=true)">Expand all details</button>''' + ''.join(stages) + controls + '''</details><section class="card"><h2>Please check this one example</h2><p>Open the overview, expand a stage, and check whether the processing, field mappings and two control lanes explain the flow clearly enough. Please annotate anything missing or misleading before we expand to other pipelines.</p><p class="muted">Run failures, retries, recovery and resource monitoring belong to data-operations and are omitted here.</p></section></main></html>'''


if __name__ == '__main__':
    directory = Path(__file__).parent
    config = json.loads((directory / 'example.json').read_text())
    receipt = json.loads((directory / 'receipt.json').read_text())
    target = Path('.lavish/lineage-pilot.html')
    target.parent.mkdir(exist_ok=True)
    target.write_text(render(config, receipt))
