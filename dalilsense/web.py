"""Stdlib-only web UI for running Experiment 1 against local Ollama."""
import hashlib
import json
import queue
import re
import shutil
import threading
import time
import urllib.parse
from collections import defaultdict
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dalilsense.narrator import (
    DECODING,
    DEFAULT_MODEL,
    OllamaError,
    SYSTEM_PROMPT,
    list_models,
    stream_tokens,
)

PROMPT_SHA = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:12]

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "experiments" / "JSON_test"
RESULTS_DIR = BASE_DIR / "experiments" / "results" / "exp1"


def safe_dir(model: str) -> str:
    return model.replace("/", "--").replace(":", "_")


def model_results_dir(model: str) -> Path:
    d = RESULTS_DIR / safe_dir(model) / PROMPT_SHA
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def read_outputs(model: str) -> dict[str, dict]:
    return {r["case_id"]: r for r in read_jsonl(model_results_dir(model) / "outputs.jsonl")}


def read_labels(model: str) -> dict[str, dict]:
    return {r["case_id"]: r for r in read_jsonl(model_results_dir(model) / "labels_human.jsonl")}


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def load_cases() -> list[tuple[str, dict]]:
    return [(p.stem, json.loads(p.read_text())) for p in sorted(DATASET_DIR.glob("case_*.json"))]


class Hub:
    """Fan-out pub/sub for SSE subscribers, keyed by model."""

    def __init__(self):
        self.lock = threading.Lock()
        self.subs: dict[str, list[queue.Queue]] = defaultdict(list)
        self.running: set[str] = set()

    def subscribe(self, model: str) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self.lock:
            self.subs[model].append(q)
        return q

    def unsubscribe(self, model: str, q: queue.Queue) -> None:
        with self.lock:
            if q in self.subs[model]:
                self.subs[model].remove(q)

    def publish(self, model: str, event: dict) -> None:
        with self.lock:
            subs = list(self.subs[model])
        for q in subs:
            q.put(event)


HUB = Hub()


def run_experiment(model: str) -> None:
    try:
        out_path = model_results_dir(model) / "outputs.jsonl"
        # Keep previous runs and their human labels together before starting fresh.
        run_dir = model_results_dir(model)
        existing = [run_dir / name for name in ("outputs.jsonl", "labels_human.jsonl", "summary.md", "errors.jsonl") if (run_dir / name).exists()]
        if existing:
            archive = run_dir / "history" / str(time.time_ns())
            archive.mkdir(parents=True)
            for path in existing:
                shutil.copy2(path, archive / path.name)
            for path in existing:
                path.unlink()
        HUB.publish(model, {"type": "reset"})
        for case_id, case_input in load_cases():
            HUB.publish(model, {"type": "start", "case_id": case_id})
            prompt_str = json.dumps(case_input)
            start = time.monotonic()
            pieces: list[str] = []
            try:
                for piece in stream_tokens(prompt_str, model=model):
                    pieces.append(piece)
                    HUB.publish(model, {"type": "token", "case_id": case_id, "piece": piece})
            except OllamaError as e:
                append_jsonl(run_dir / "errors.jsonl", {"case_id": case_id, "message": str(e)})
                HUB.publish(model, {"type": "error", "case_id": case_id, "message": str(e)})
                continue
            output = "".join(pieces)
            latency_ms = int((time.monotonic() - start) * 1000)
            append_jsonl(out_path, {
                "case_id": case_id,
                "input": case_input,
                "output": output,
                "latency_ms": latency_ms,
                "model": model,
                "prompt_sha": PROMPT_SHA,
            })
            HUB.publish(model, {
                "type": "done", "case_id": case_id,
                "output": output, "latency_ms": latency_ms,
            })
        write_summary(model)
    except Exception as e:
        append_jsonl(model_results_dir(model) / "errors.jsonl", {"case_id": "run", "message": str(e)})
        HUB.publish(model, {"type": "run_error", "message": str(e)})
    finally:
        with HUB.lock:
            HUB.running.discard(model)
        HUB.publish(model, {"type": "complete"})


def _md_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", "<br>")


def write_summary(model: str) -> None:
    total = len(load_cases())
    outputs = read_outputs(model)
    labels = read_labels(model)
    labeled = [v for v in labels.values() if "hallucination" in v]
    n_lbl = len(labeled)
    n_h = sum(1 for v in labeled if v["hallucination"])
    rate = f"{n_h / n_lbl:.1%}" if n_lbl else "—"
    decoding_lines = "\n".join(f"- {k}: {v}" for k, v in DECODING.items())
    rows = []
    for case_id, case_input in load_cases():
        rec = outputs.get(case_id, {})
        output_text = rec.get("output", "")
        latency = rec.get("latency_ms")
        latency_text = f"{latency}ms" if latency is not None else "—"
        lbl = labels.get(case_id, {})
        if "hallucination" in lbl:
            label_text = "Y" if lbl["hallucination"] else "N"
        else:
            label_text = "—"
        rows.append(
            f"| {case_id} | `{_md_cell(json.dumps(case_input))}` | {_md_cell(output_text) or '—'} | {latency_text} | {label_text} |"
        )
    summary = (
        f"# Guided prompt evaluation — `{model}`\n\n"
        f"- **Model:** `{model}`\n"
        f"- **Prompt SHA (first 12):** `{PROMPT_SHA}`\n"
        f"- **Runs completed:** {len(outputs)}/{total}\n"
        f"- **Labeled:** {n_lbl}/{total}\n"
        f"- **Hallucinations:** {n_h}/{n_lbl} (rate: {rate})\n"
        f"- **Last updated:** {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n"
        f"## System prompt\n\n"
        f"```\n{SYSTEM_PROMPT.strip()}\n```\n\n"
        f"## Decoding\n\n{decoding_lines}\n\n"
        f"## Cases\n\n"
        f"| id | input | output | latency | label |\n"
        f"|----|-------|--------|---------|-------|\n"
        + "\n".join(rows)
        + "\n"
    )
    (model_results_dir(model) / "summary.md").write_text(summary)


PAGE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>DalilSENSE — Sensor review</title>
<style>
:root {{
  color-scheme: light;
  --accent: #c41230;
  --accent-hover: #a20f28;
  --on-accent: #ffffff;
  --ink: #20252b;
  --muted: #52606d;
  --line: #7c8793;
  --surface: #ffffff;
  --canvas: #ffffff;
  --subtle: #f5f6f8;
  --hover: #eef1f4;
  --focus: #155eef;
  --info: #245a8d;
  --danger: #9f1239;
  --review-yes: #7a4800;
  --review-yes-bg: #fff4df;
  --review-no: #146451;
  --review-no-bg: #edf7f3;
  --radius: 10px;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  --mono: ui-monospace, "SF Mono", Menlo, monospace;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font: 15px/1.55 var(--sans);
  -webkit-text-size-adjust: 100%;
}}
[hidden] {{ display: none !important; }}
.brand-bar {{ width: 100%; background: var(--surface); border-bottom: 1px solid var(--line); }}
.brand-inner {{ position: relative; max-width: 1440px; margin-inline: auto; padding-inline: 32px; display: flex; justify-content: space-between; align-items: stretch; gap: 24px; }}
.university-logo {{ display: block; flex: 0 0 88px; align-self: flex-start; }}
.university-logo img {{ display: block; width: 88px; height: 88px; }}
.header-navigation {{ display: flex; flex-direction: column; align-items: flex-end; justify-content: center; min-width: 0; }}
.primary-nav {{ display: flex; align-items: center; gap: 24px; }}
.brand-bar a, .brand-bar summary {{ color: var(--ink); text-decoration: none; font-weight: 500; }}
.brand-bar a:hover {{ color: var(--accent); }}
.primary-nav {{ font-size: 15px; gap: 24px; }}
.primary-nav > a {{ display: flex; align-items: center; min-height: 44px; }}
.header-disclosure {{ position: static; }}
.header-disclosure > summary {{ list-style: none; margin: 0; padding: 0; cursor: pointer; }}
.header-disclosure > summary::-webkit-details-marker {{ display: none; }}
.header-disclosure > .icon-button {{ width: 44px; height: 44px; display: flex; justify-content: center; align-items: center; border-radius: var(--radius); }}
.header-disclosure > .search-button {{ margin-left: 12px; }}
.header-disclosure > .menu-button {{ background: var(--accent); color: var(--on-accent); }}
.header-disclosure > .menu-button:hover {{ background: var(--accent-hover); }}
.header-disclosure[open] > summary {{ outline: 2px solid var(--line); outline-offset: 2px; }}
.header-panel {{ position: absolute; top: calc(100% + 8px); right: 32px; z-index: 5; width: min(340px, calc(100vw - 40px)); padding: 20px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); color: var(--ink); box-shadow: 0 8px 24px #0000000f; font-size: 14px; }}
.header-panel nav {{ display: grid; gap: 4px; }}
.header-panel nav a {{ padding: 10px 4px; }}
.header-panel label {{ display: flex; align-items: center; gap: 8px; }}
.header-panel input[type="search"] {{ width: 100%; min-height: 44px; margin-top: 8px; padding: 10px 12px; font: inherit; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); color: var(--ink); }}
.search-count {{ margin: 8px 0 0; font-size: 12px; color: var(--muted); }}
.project-heading {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 16px; margin-bottom: 20px; }}
.project-heading .mark {{ font-size: 18px; font-weight: 750; letter-spacing: -0.6px; }}
main {{ max-width: 1440px; margin: 0 auto; padding: 24px 32px 64px; }}
.site-footer {{ max-width: 1440px; margin-inline: auto; padding: 0 32px 24px; color: var(--muted); font-size: 12px; }}
.footer-inner {{ display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px 24px; border-top: 1px solid var(--line); padding-top: 16px; }}
.footer-inner p {{ margin: 0; }}
h1 {{ margin: 0; font-size: 13px; line-height: 1.5; letter-spacing: 0; font-weight: 400; color: var(--muted); }}
.subtitle {{ max-width: 85ch; margin: 0; color: var(--muted); font-size: 13px; }}
.model-card {{ display: flex; flex-direction: column; gap: 12px; min-width: 0; }}
.model-selector {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
.model-selector img {{ width: 36px; height: 36px; object-fit: contain; flex-shrink: 0; }}
.model-card select {{ width: 100%; min-width: 0; flex: 1; }}
.model-actions {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: stretch; gap: 10px; }}
.model-actions > button, .model-actions > a {{ display: flex; align-items: center; justify-content: center; min-width: 0; min-height: 44px; padding: 10px 12px; font: 600 13px/1.4 var(--sans); text-align: center; border-radius: var(--radius); }}
.model-actions > a {{ border: 1px solid var(--line); background: var(--surface); color: var(--ink); text-decoration: none; }}
.model-actions > a:hover {{ background: var(--hover); border-color: var(--line); }}
.stats {{ display: grid; grid-template-columns: minmax(0, 1.5fr) repeat(3, minmax(0, 1fr)); gap: 16px; margin-bottom: 8px; }}
.stat-card {{ padding: 20px 24px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); }}
.stat-card .label {{ color: var(--muted); font-size: 13px; font-weight: 600; }}
.stat-card.metric-card {{ padding: 0; overflow: hidden; }}
.metric-card .label {{ display: block; width: 100%; padding: 12px 24px; background: var(--accent); color: var(--on-accent); border-bottom: 1px solid var(--line); }}
.metric-body {{ padding: 16px 24px 20px; }}
.stat-card .value {{ margin-top: 8px; font-size: 32px; font-weight: 650; line-height: 1.2; letter-spacing: -1px; font-variant-numeric: tabular-nums; }}
.stat-card .sub {{ margin-top: 8px; color: var(--muted); font-size: 12px; }}
.metric-body .value {{ margin-top: 0; }}
.results-heading {{ display: flex; align-items: baseline; justify-content: space-between; gap: 8px 24px; flex-wrap: wrap; margin-bottom: 12px; }}
.results-heading h2 {{ font-size: 17px; font-weight: 650; margin: 0; }}
.results-heading p {{ color: var(--muted); font-size: 13px; margin: 0; }}
.table-wrap {{ overflow: auto; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }}
table {{ width: 100%; min-width: 860px; border-collapse: separate; border-spacing: 0; table-layout: fixed; font-size: 13px; }}
th {{ text-align: left; background: var(--accent); color: var(--on-accent); font-size: 12px; font-weight: 600; padding: 14px 16px; border-bottom: 1px solid var(--line); }}
th:nth-child(1) {{ width: 100px; }}
th:nth-child(2) {{ width: 25%; }}
th:nth-child(4) {{ width: 90px; }}
th:nth-child(5) {{ width: 152px; }}
td {{ border-bottom: 1px solid var(--line); padding: 16px; vertical-align: top; overflow-wrap: anywhere; }}
tbody tr:last-child td {{ border-bottom: 0; }}
tbody tr:hover, tbody tr:focus-within {{ background: var(--subtle); }}
.input {{ font-size: 13px; }}
.sensor {{ display: grid; grid-template-columns: 52px 1fr; gap: 8px; }}
.sensor span:first-child {{ color: var(--muted); }}
.output {{ white-space: pre-wrap; line-height: 1.7; }}
.output:empty::before {{ content: "Not run"; color: var(--muted); }}
.output.running:empty::before {{ content: "Generating…"; }}
.output-meta {{ color: var(--muted); font-size: 12px; margin-top: 8px; }}
.run-status:empty {{ display: none; }}
.run-status {{ margin: 0; color: var(--muted); font-size: 13px; }}
.notice {{ padding: 12px 16px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); font-size: 13px; color: var(--muted); margin: 0 0 20px; }}
.prompt-details {{ margin-bottom: 24px; color: var(--muted); font-size: 13px; }}
summary {{ cursor: pointer; padding-block: 10px; width: fit-content; }}
.prompt-details > summary {{ padding-top: 4px; }}
.prompt-details pre {{ white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.7 var(--mono); padding: 16px; background: var(--subtle); border: 1px solid var(--line); border-radius: var(--radius); }}
.latency {{ color: var(--muted); white-space: nowrap; font-size: 12px; font-variant-numeric: tabular-nums; }}
.running {{ color: var(--info); font-style: italic; }}
.error {{ color: var(--danger); }}
button, select {{ font: 13px/1.4 var(--sans); min-height: 44px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); color: var(--ink); }}
button {{ padding: 10px 16px; cursor: pointer; font-weight: 600; }}
button:hover {{ background: var(--hover); border-color: var(--line); }}
button#run {{ background: var(--accent); color: var(--on-accent); border-color: var(--line); }}
button#run:hover {{ background: var(--accent-hover); border-color: var(--line); }}
button:disabled, button#run:disabled {{ cursor: not-allowed; opacity: 1; background: var(--hover); color: var(--muted); border-color: var(--line); }}
button.lbl {{ min-width: 44px; padding: 8px; }}
button.lbl + button.lbl {{ margin-left: 6px; }}
.labeled-y .lbl[data-v="y"] {{ background: var(--review-yes-bg); border-color: var(--line); color: var(--review-yes); box-shadow: inset 0 0 0 1px var(--line); }}
.labeled-n .lbl[data-v="n"] {{ background: var(--review-no-bg); border-color: var(--line); color: var(--review-no); box-shadow: inset 0 0 0 1px var(--line); }}
.lbl[aria-pressed="true"] {{ text-decoration: underline; text-underline-offset: 4px; }}
input::placeholder {{ color: var(--muted); opacity: 1; }}
select {{ max-width: 100%; padding: 10px 32px 10px 12px; }}
a {{ color: var(--accent); text-underline-offset: 3px; }}
a:hover {{ color: var(--accent-hover); }}
:focus-visible, .header-disclosure > summary:focus-visible {{ outline: 3px solid var(--focus); outline-offset: 3px; }}
.table-wrap:focus-visible {{ outline-offset: 4px; }}
@media (max-width: 1100px) {{
  .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
@media (max-width: 600px) {{
  .stats {{ grid-template-columns: 1fr; }}
}}
@media (max-width: 700px) {{
  .brand-inner {{ padding-inline: 20px; gap: 16px; }}
  .header-panel {{ right: 20px; }}
  .university-logo {{ flex-basis: 80px; }}
  .university-logo img {{ width: 80px; height: 80px; }}
  .primary-nav {{ gap: 12px; }}
  .primary-nav > a {{ display: none; }}
  .header-disclosure > .search-button {{ margin-left: 0; }}
  main {{ padding: 24px 20px 40px; }}
  .site-footer {{ padding-inline: 20px; }}
  .stats {{ gap: 10px; }}
  .stat-card {{ padding: 16px 12px; }}
  .metric-card .label {{ padding: 12px 16px; }}
  .metric-body {{ padding: 16px; }}
  .stat-card .value {{ font-size: 26px; }}
}}
@media (max-width: 420px) {{
  main, .site-footer {{ padding-inline: 16px; }}
  .stats {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<header class="brand-bar">
  <div class="brand-inner">
    <a class="university-logo" href="https://www.qatar.cmu.edu/" aria-label="Carnegie Mellon University in Qatar home">
      <img src="/static/cmu-q-logo.webp" width="88" height="88" alt="Carnegie Mellon University Qatar">
    </a>
    <div class="header-navigation">
      <nav class="primary-nav" aria-label="Main navigation">
        <details class="header-disclosure" id="case-search">
          <summary class="icon-button search-button" aria-label="Search cases"><svg width="30" height="30" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><circle cx="13" cy="13" r="10"/><path d="m21 21 8 8"/></svg></summary>
          <div class="header-panel" role="search"><label for="case-query">Search cases</label><input id="case-query" type="search" placeholder="Case, sensor value, or output" autocomplete="off"><p class="search-count" id="search-count" role="status"></p></div>
        </details>
        <details class="header-disclosure">
          <summary class="icon-button menu-button" aria-label="Open navigation menu"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M4 5h16M4 12h16M4 19h16"/></svg></summary>
          <div class="header-panel"><nav aria-label="Expanded navigation">
            <a href="/exp1/">DalilSENSE dashboard</a>
          </nav></div>
        </details>
      </nav>
    </div>
  </div>
</header>
<main>
<div class="project-heading"><span class="mark">DalilSENSE</span><h1>RQ1 · Sensor narration with a guided prompt</h1></div>
<div class="stats">
  <div class="stat-card model-card">
    <div class="model-selector"><img src="/static/qwen-logo.webp" width="36" height="36" alt="" {model_logo_hidden}><select id="model" aria-label="Choose model">{model_options}</select></div>
    <div class="model-actions">
      <button id="run" {run_disabled}>Run all {total}</button>
      <a href="/exp1/summary?model={model_url}" target="_blank">Download summary ↗</a>
    </div>
    <p class="run-status" id="run-status" role="status">{run_status}</p>
  </div>
  <div class="stat-card metric-card"><div class="label">Generated</div><div class="metric-body"><div class="value" id="stat-runs">{n_out}/{total}</div><div class="sub">cases executed</div></div></div>
  <div class="stat-card metric-card"><div class="label">Reviewed</div><div class="metric-body"><div class="value" id="stat-labeled">{n_lbl}/{total}</div><div class="sub">human verdicts recorded</div></div></div>
  <div class="stat-card metric-card"><div class="label">Hallucination rate</div><div class="metric-body"><div class="value" id="stat-rate">{rate}</div><div class="sub" id="stat-rate-sub">{n_h} of {n_lbl_or_dash} reviewed · human labels</div></div></div>
</div>
<details class="prompt-details"><summary>View active system prompt</summary><pre>{system_prompt}</pre></details>
<div class="results-heading">
  <h2 id="results-title">Case review</h2>
  <p id="label-help">Mark Yes for unsupported facts. Format is checked separately.</p>
</div>
<div class="table-wrap" role="region" aria-labelledby="results-title" tabindex="0">
<table aria-labelledby="results-title" aria-describedby="label-help">
<thead><tr><th scope="col">Case</th><th scope="col">Sensor input</th><th scope="col">Model output</th><th scope="col">Latency</th><th scope="col">Hallucination?</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</div>
</main>
<footer class="site-footer">
  <div class="footer-inner">
    <p>DalilSENSE · Research workspace</p>
    <p>Model outputs evaluated through human review.</p>
  </div>
</footer>
<script>
const disclosures = document.querySelectorAll('.header-disclosure');
disclosures.forEach(detail => detail.addEventListener('toggle', () => {{
  if (detail.open) {{
    disclosures.forEach(other => {{ if (other !== detail) other.open = false; }});
    if (detail.id === 'case-search') document.getElementById('case-query').focus();
  }}
}}));
document.addEventListener('click', event => {{
  disclosures.forEach(detail => {{ if (!detail.contains(event.target)) detail.open = false; }});
}});
document.addEventListener('keydown', event => {{
  if (event.key === 'Escape') disclosures.forEach(detail => {{
    if (detail.open) {{ detail.open = false; detail.querySelector('summary').focus(); }}
  }});
}});
const query = document.getElementById('case-query');
function filterCases() {{
  const term = query.value.trim().toLowerCase();
  let count = 0;
  document.querySelectorAll('tbody tr').forEach(row => {{
    row.hidden = !row.textContent.toLowerCase().includes(term);
    if (!row.hidden) count++;
  }});
  document.getElementById('search-count').textContent = term ? count + ' matching cases. Clear search to show all.' : '';
}}
query.addEventListener('input', filterCases);
const model = {model_js};
const total = {total};
const errorCount = {errors_js};
const run = document.getElementById('run');
const status = document.getElementById('run-status');
let running = {running_js};
const completed = new Set({completed_js});
function busy(value) {{
  running = value;
  run.disabled = value;
  run.textContent = value ? 'Running…' : 'Run all ' + total;
  document.querySelectorAll('.lbl').forEach(btn => {{ btn.disabled = value || !completed.has(btn.closest('tr').id.slice(4)); }});
}}
function metadata(row, output) {{
  const valid = /^Left: (none|person|object); Ahead: (none|person|object); Right: (none|person|object)$/.test(output);
  row.querySelector('.output-meta').textContent = output.length + ' chars · ' + (valid ? 'Format valid' : 'Check format');
}}
busy(running);
document.getElementById('model').addEventListener('change', e => {{
  const u = new URL(location.href); u.searchParams.set('model', e.target.value); location.href = u.toString();
}});
const es = new EventSource('/exp1/stream?model=' + encodeURIComponent(model));
es.onerror = () => {{ status.textContent = 'Connection interrupted. Reconnecting…'; }};
es.onmessage = ev => {{
  const msg = JSON.parse(ev.data);
  if (msg.type === 'state') {{
    if (running && !msg.running) {{ location.reload(); return; }}
    busy(msg.running);
    status.textContent = msg.running ? 'Run in progress…' : (errorCount ? errorCount + ' errors. Review the errors and retry.' : '');
    return;
  }}
  if (msg.type === 'complete') {{ location.reload(); return; }}
  if (msg.type === 'run_error') {{ status.textContent = 'Run failed: ' + msg.message; busy(false); return; }}
  if (msg.type === 'reset') {{
    completed.clear(); busy(true);
    document.getElementById('stat-runs').textContent = '0/' + total;
    document.getElementById('stat-labeled').textContent = '0/' + total;
    document.getElementById('stat-rate').textContent = '—';
    document.getElementById('stat-rate-sub').textContent = 'No reviews yet';
    document.querySelectorAll('tbody tr').forEach(row => {{
      row.querySelector('.output').className = 'output';
      row.classList.remove('labeled-y', 'labeled-n');
      row.querySelector('.output').textContent = '';
      row.querySelector('.output-meta').textContent = '';
      row.querySelector('.latency').textContent = '—';
      row.querySelectorAll('.lbl').forEach(btn => btn.setAttribute('aria-pressed', 'false'));
    }});
    return;
  }}
  const row = document.getElementById('row-' + msg.case_id);
  if (!row) return;
  const out = row.querySelector('.output');
  if (msg.type === 'start') {{
    busy(true); out.textContent = ''; out.className = 'output running';
    status.textContent = 'Generating ' + msg.case_id + ' · ' + completed.size + ' of ' + total + ' complete';
  }} else if (msg.type === 'token') {{ out.textContent += msg.piece; }}
  else if (msg.type === 'done') {{
    out.className = 'output'; out.textContent = msg.output; metadata(row, msg.output);
    row.querySelector('.latency').textContent = msg.latency_ms + ' ms';
    completed.add(msg.case_id); document.getElementById('stat-runs').textContent = completed.size + '/' + total;
  }} else if (msg.type === 'error') {{ out.className = 'output error'; out.textContent = 'Error: ' + msg.message; }}
  if (query.value) filterCases();
}};
run.addEventListener('click', async () => {{
  busy(true); status.textContent = 'Starting run…';
  try {{
    const r = await fetch('/exp1/run', {{ method: 'POST', headers: {{'Content-Type':'application/json'}}, body: JSON.stringify({{model}}) }});
    if (!r.ok) throw new Error(await r.text());
  }} catch (err) {{ status.textContent = 'Could not start run: ' + err.message; busy(false); }}
}});
document.querySelectorAll('.lbl').forEach(btn => btn.addEventListener('click', async () => {{
  const row = btn.closest('tr');
  const buttons = row.querySelectorAll('.lbl');
  buttons.forEach(b => b.disabled = true);
  try {{
    const r = await fetch('/exp1/label', {{ method: 'POST', headers: {{'Content-Type':'application/json'}}, body: JSON.stringify({{case_id: row.id.slice(4), model, hallucination: btn.dataset.v === 'y'}}) }});
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    row.classList.remove('labeled-y', 'labeled-n'); row.classList.add(btn.dataset.v === 'y' ? 'labeled-y' : 'labeled-n');
    buttons.forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
    document.getElementById('stat-labeled').textContent = data.n_lbl + '/' + total;
    document.getElementById('stat-rate').textContent = data.rate;
    document.getElementById('stat-rate-sub').textContent = data.n_h + ' of ' + data.n_lbl + ' reviewed · human labels';
    status.textContent = 'Saved review for ' + row.id.slice(4) + '.';
  }} catch (err) {{ status.textContent = 'Review not saved: ' + err.message; }}
  finally {{ buttons.forEach(b => b.disabled = running); }}
}}));
</script>
</body>
</html>
"""


def render_page(model: str) -> str:
    try:
        installed = list_models()
    except OllamaError:
        installed = []
    if not installed:
        installed = [DEFAULT_MODEL]
    if model not in installed:
        model = installed[0]

    model_options = "\n".join(
        f'<option value="{html_escape(m)}"{" selected" if m == model else ""}>{html_escape(m)}</option>'
        for m in installed
    )
    outputs = read_outputs(model)
    labels = read_labels(model)
    errors = {r["case_id"]: r["message"] for r in read_jsonl(model_results_dir(model) / "errors.jsonl")}
    rows = []
    for case_id, case_input in load_cases():
        rec = outputs.get(case_id, {})
        output_text = rec.get("output", "")
        latency = rec.get("latency_ms")
        latency_text = f"{latency} ms" if latency is not None else "—"
        lbl = labels.get(case_id, {})
        row_class = ""
        if "hallucination" in lbl:
            row_class = "labeled-y" if lbl["hallucination"] else "labeled-n"
        sensor_html = ''.join(
            f'<div class="sensor"><span>{title}</span><span>{html_escape(case_input[key].replace("_", " "))}</span></div>'
            for key, title in (("left", "Left"), ("middle", "Ahead"), ("right", "Right"))
        )
        valid = bool(re.fullmatch(r"Left: (none|person|object); Ahead: (none|person|object); Right: (none|person|object)", output_text))
        meta = f'{len(output_text)} chars · {"Format valid" if valid else "Check format"}' if rec else ''
        disabled = ' disabled' if not rec or model in HUB.running else ''
        output_class = 'output error' if case_id in errors else 'output'
        display_output = 'Error: ' + errors[case_id] if case_id in errors else output_text
        rows.append(
            f'<tr id="row-{case_id}" class="{row_class}">'
            f'<td>{case_id}</td>'
            f'<td class="input">{sensor_html}</td>'
            f'<td><div class="{output_class}">{html_escape(display_output)}</div><div class="output-meta">{meta}</div></td>'
            f'<td class="latency">{latency_text}</td>'
            f'<td><button class="lbl" data-v="y" aria-label="{case_id}: hallucination yes" aria-pressed="{str(row_class == "labeled-y").lower()}"{disabled}>Yes</button>'
            f'<button class="lbl" data-v="n" aria-label="{case_id}: hallucination no" aria-pressed="{str(row_class == "labeled-n").lower()}"{disabled}>No</button></td>'
            f'</tr>'
        )
    n_out = len(outputs)
    n_lbl = len(labels)
    n_h = sum(1 for v in labels.values() if v.get("hallucination"))
    rate = f"{n_h / n_lbl:.0%}" if n_lbl else "—"
    return PAGE.format(
        prompt_sha=PROMPT_SHA,
        total=len(load_cases()),
        system_prompt=html_escape(SYSTEM_PROMPT.strip()),
        running_js=json.dumps(model in HUB.running),
        errors_js=json.dumps(len(errors)),
        completed_js=json.dumps(list(outputs)),
        run_disabled="disabled" if model in HUB.running else "",
        run_status="Run in progress…" if model in HUB.running else "",
        model_options=model_options,
        model_logo_hidden="" if model.lower().split("/")[-1].startswith("qwen") else "hidden",
        model_js=json.dumps(model),
        model_url=urllib.parse.quote(model, safe=""),
        rows="\n".join(rows),
        n_out=n_out,
        n_lbl=n_lbl,
        n_h=n_h,
        n_lbl_or_dash=n_lbl if n_lbl else "—",
        rate=rate,
    )


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def _qs(self) -> dict[str, str]:
        q = urllib.parse.urlparse(self.path).query
        return {k: v[0] for k, v in urllib.parse.parse_qs(q).items()}

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n == 0:
            return {}
        return json.loads(self.rfile.read(n))

    def _send(self, code: int, body: bytes, ctype: str = "text/plain; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/exp1/")
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            return
        if path in ("/static/cmu-q-logo.webp", "/static/qwen-logo.webp"):
            self._send(200, (BASE_DIR / "dalilsense" / "static" / Path(path).name).read_bytes(), "image/webp")
            return
        if path in ("/exp1", "/exp1/"):
            model = self._qs().get("model") or DEFAULT_MODEL
            self._send(200, render_page(model).encode(), "text/html; charset=utf-8")
            return
        if path == "/exp1/stream":
            self._handle_sse()
            return
        if path == "/exp1/summary":
            model = self._qs().get("model") or DEFAULT_MODEL
            summary_path = model_results_dir(model) / "summary.md"
            if not summary_path.exists():
                write_summary(model)
            self._send(200, summary_path.read_bytes(), "text/markdown; charset=utf-8")
            return
        self._send(404, b"not found")

    def _handle_sse(self):
        model = self._qs().get("model") or DEFAULT_MODEL
        q = HUB.subscribe(model)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            state = {"type": "state", "running": model in HUB.running}
            self.wfile.write(f"data: {json.dumps(state)}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    event = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            HUB.unsubscribe(model, q)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/exp1/run":
            body = self._read_json()
            model = body.get("model") or DEFAULT_MODEL
            with HUB.lock:
                if model in HUB.running:
                    self._send_json(409, {"status": "already_running"})
                    return
                HUB.running.add(model)
            threading.Thread(target=run_experiment, args=(model,), daemon=True).start()
            self._send_json(200, {"status": "started"})
            return
        if path == "/exp1/label":
            body = self._read_json()
            case_id = body.get("case_id")
            model = body.get("model") or DEFAULT_MODEL
            with HUB.lock:
                if model in HUB.running or case_id not in read_outputs(model):
                    self._send_json(409, {"error": "Wait for a completed run before reviewing."})
                    return
                if not isinstance(body.get("hallucination"), bool):
                    self._send_json(400, {"error": "A yes or no verdict is required."})
                    return
                append_jsonl(
                    model_results_dir(model) / "labels_human.jsonl",
                    {
                        "case_id": case_id,
                        "hallucination": bool(body.get("hallucination")),
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    },
                )
                write_summary(model)
                labels = read_labels(model)
                n_lbl = len(labels)
                n_h = sum(1 for v in labels.values() if v.get("hallucination"))
                rate = f"{n_h / n_lbl:.0%}" if n_lbl else "—"
                self._send_json(200, {"status": "ok", "n_lbl": n_lbl, "n_h": n_h, "rate": rate})
            return
        self._send(404, b"not found")


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"DalilSENSE experiment UI → http://{host}:{port}/exp1/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()