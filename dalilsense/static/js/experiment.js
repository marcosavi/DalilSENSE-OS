const query = document.getElementById('case-query');
function filterCases() {
  const term = query.value.trim().toLowerCase();
  let count = 0;
  document.querySelectorAll('tbody tr').forEach(row => {
    row.hidden = !row.textContent.toLowerCase().includes(term);
    if (!row.hidden) count++;
  });
  document.getElementById('search-count').textContent = term ? count + ' matching cases. Clear search to show all.' : '';
}
query.addEventListener('input', filterCases);
const state = JSON.parse(document.getElementById('experiment-state').textContent);
const {model, total, errorCount, urls} = state;
const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
const run = document.getElementById('run');
const status = document.getElementById('run-status');
let running = state.running;
const completed = new Set(state.completed);
function busy(value) {
  running = value;
  run.disabled = value;
  run.textContent = value ? 'Running…' : 'Run all ' + total;
  document.querySelectorAll('.lbl').forEach(btn => { btn.disabled = value || !completed.has(btn.closest('tr').id.slice(4)); });
}
function metadata(row, output) {
  const valid = /^Left: (none|person|object); Ahead: (none|person|object); Right: (none|person|object)$/.test(output);
  row.querySelector('.output-meta').textContent = output.length + ' chars · ' + (valid ? 'Format valid' : 'Check format');
}
busy(running);
document.getElementById('model').addEventListener('change', e => {
  const u = new URL(location.href); u.searchParams.set('model', e.target.value); location.href = u.toString();
});
const es = new EventSource(urls.stream + '?model=' + encodeURIComponent(model));
es.onerror = () => { status.textContent = 'Connection interrupted. Reconnecting…'; };
es.onmessage = ev => {
  const msg = JSON.parse(ev.data);
  if (msg.type === 'state') {
    if (running && !msg.running) { location.reload(); return; }
    busy(msg.running);
    status.textContent = msg.running ? 'Run in progress…' : (errorCount ? errorCount + ' errors. Review the errors and retry.' : '');
    return;
  }
  if (msg.type === 'complete') { location.reload(); return; }
  if (msg.type === 'run_error') { status.textContent = 'Run failed: ' + msg.message; busy(false); return; }
  if (msg.type === 'reset') {
    completed.clear(); busy(true);
    document.getElementById('stat-runs').textContent = '0/' + total;
    document.getElementById('stat-labeled').textContent = '0/' + total;
    document.getElementById('stat-rate').textContent = '—';
    document.getElementById('stat-rate-sub').textContent = 'No reviews yet';
    document.querySelectorAll('tbody tr').forEach(row => {
      row.querySelector('.output').className = 'output';
      row.classList.remove('labeled-y', 'labeled-n');
      row.querySelector('.output').textContent = '';
      row.querySelector('.output-meta').textContent = '';
      row.querySelector('.latency').textContent = '—';
      row.querySelectorAll('.lbl').forEach(btn => btn.setAttribute('aria-pressed', 'false'));
    });
    return;
  }
  const row = document.getElementById('row-' + msg.case_id);
  if (!row) return;
  const out = row.querySelector('.output');
  if (msg.type === 'start') {
    busy(true); out.textContent = ''; out.className = 'output running';
    status.textContent = 'Generating ' + msg.case_id + ' · ' + completed.size + ' of ' + total + ' complete';
  } else if (msg.type === 'token') { out.textContent += msg.piece; }
  else if (msg.type === 'done') {
    out.className = 'output'; out.textContent = msg.output; metadata(row, msg.output);
    row.querySelector('.latency').textContent = msg.latency_ms + ' ms';
    completed.add(msg.case_id); document.getElementById('stat-runs').textContent = completed.size + '/' + total;
  } else if (msg.type === 'error') { out.className = 'output error'; out.textContent = 'Error: ' + msg.message; }
  if (query.value) filterCases();
};
run.addEventListener('click', async () => {
  busy(true); status.textContent = 'Starting run…';
  try {
    const r = await fetch(urls.run, { method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken}, body: JSON.stringify({model}) });
    if (!r.ok) throw new Error(await r.text());
  } catch (err) { status.textContent = 'Could not start run: ' + err.message; busy(false); }
});
document.querySelectorAll('.lbl').forEach(btn => btn.addEventListener('click', async () => {
  const row = btn.closest('tr');
  const buttons = row.querySelectorAll('.lbl');
  buttons.forEach(b => b.disabled = true);
  try {
    const r = await fetch(urls.label, { method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken}, body: JSON.stringify({case_id: row.id.slice(4), model, hallucination: btn.dataset.v === 'y'}) });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    row.classList.remove('labeled-y', 'labeled-n'); row.classList.add(btn.dataset.v === 'y' ? 'labeled-y' : 'labeled-n');
    buttons.forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
    document.getElementById('stat-labeled').textContent = data.n_lbl + '/' + total;
    document.getElementById('stat-rate').textContent = data.rate;
    document.getElementById('stat-rate-sub').textContent = data.n_h + ' of ' + data.n_lbl + ' reviewed · human labels';
    status.textContent = 'Saved review for ' + row.id.slice(4) + '.';
  } catch (err) { status.textContent = 'Review not saved: ' + err.message; }
  finally { buttons.forEach(b => b.disabled = running); }
}));
