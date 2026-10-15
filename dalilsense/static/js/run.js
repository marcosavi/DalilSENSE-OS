const runState = JSON.parse(document.getElementById('run-state').textContent);
const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

// Carousel navigation and progress bar.
const carousel = document.querySelector('.case-list.carousel');
const cards = carousel ? [...carousel.querySelectorAll('.case-card')] : [];
const prevBtn = document.getElementById('nav-prev');
const nextBtn = document.getElementById('nav-next');
const counterEl = document.getElementById('carousel-current');
const progressFill = document.getElementById('progress-fill');
const progressPercent = document.getElementById('progress-percent');
let currentIndex = 0;

function showCard(index) {
  if (!cards.length) return;
  currentIndex = Math.max(0, Math.min(index, cards.length - 1));
  cards.forEach((card, i) => card.classList.toggle('active', i === currentIndex));
  if (counterEl) counterEl.textContent = currentIndex + 1;
  if (prevBtn) prevBtn.disabled = currentIndex === 0;
  if (nextBtn) nextBtn.disabled = currentIndex === cards.length - 1;
}

function updateProgress() {
  if (!progressFill || !cards.length) return;
  const reviewed = cards.filter(card => {
    const status = card.querySelector('.review-status');
    return status && status.textContent.trim().startsWith('Saved');
  }).length;
  const pct = Math.round((reviewed / cards.length) * 100);
  progressFill.style.width = pct + '%';
  progressPercent.textContent = pct + '%';
}

if (carousel) {
  showCard(0);
  updateProgress();
  if (prevBtn) prevBtn.addEventListener('click', () => showCard(currentIndex - 1));
  if (nextBtn) nextBtn.addEventListener('click', () => showCard(currentIndex + 1));
  document.addEventListener('keydown', event => {
    if (event.target.matches('input, textarea')) return;
    if (event.key === 'ArrowLeft') showCard(currentIndex - 1);
    if (event.key === 'ArrowRight') showCard(currentIndex + 1);
  });
}
async function poll() {
  try {
    const response = await fetch(runState.statusUrl, {cache: 'no-store'});
    if (!response.ok) throw new Error('Unable to read progress.');
    const data = await response.json();
    if (data.review_ready) { location.reload(); return; }
    document.getElementById('stat-runs').textContent = data.n_out + '/' + data.total;
    document.getElementById('run-status').textContent = 'Generating ' + (data.live.case_id || 'outputs') + '…';
    Object.entries(data.outputs).forEach(([key, output]) => {
      const card = document.getElementById('row-' + key);
      if (!card) return;
      card.querySelector('.output').textContent = output.output;
      card.querySelector('.output').className = 'output';
      card.querySelector('.latency').textContent = output.latency_ms + ' ms';
    });
    if (data.live.case_id && !data.outputs[data.live.case_id]) {
      const output = document.querySelector('#row-' + data.live.case_id + ' .output');
      if (output) { output.textContent = data.live.output; output.className = 'output running'; }
    }
    data.errors.forEach(error => {
      const output = document.querySelector('#row-' + error.case_id + ' .output');
      if (output) { output.textContent = 'Error: ' + error.message; output.className = 'output error'; }
    });
  } catch (error) {
    document.getElementById('run-status').textContent = 'Connection interrupted. Retrying…';
  }
  window.setTimeout(poll, 1000);
}
if (runState.running) poll();

document.querySelectorAll('.review-form').forEach(form => {
  const choices = [...form.querySelectorAll('.verdict')];
  const message = form.querySelector('.review-status');
  choices.forEach(button => button.addEventListener('click', () => {
    choices.forEach(choice => choice.setAttribute('aria-pressed', String(choice === button)));
    message.textContent = 'Unsaved changes — save your review.';
  }));
  form.querySelector('textarea').addEventListener('input', () => {
    message.textContent = 'Unsaved changes — save your review.';
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const selected = choices.find(button => button.getAttribute('aria-pressed') === 'true');
    if (!selected) { message.textContent = 'Choose Yes or No first.'; return; }
    const controls = [...form.querySelectorAll('button, textarea')];
    controls.forEach(control => { control.disabled = true; });
    message.textContent = 'Saving…';
    try {
      const response = await fetch(runState.reviewUrl, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify({case_id: form.dataset.case, hallucination: selected.dataset.verdict === 'yes', notes: form.querySelector('textarea').value}),
      });
      if (!response.ok) {
        let reason = 'Review could not be saved.';
        try { reason = (await response.json()).error || reason; } catch (_) { /* Non-JSON CSRF or server response. */ }
        throw new Error(reason);
      }
      const data = await response.json();
      const generated = document.getElementById('stat-runs').textContent.split('/')[0];
      document.getElementById('stat-labeled').textContent = data.n_lbl + '/' + generated;
      document.getElementById('stat-rate').textContent = data.rate;
      document.getElementById('stat-rate-sub').textContent = data.n_h + ' of ' + data.n_lbl + ' reviewed';
      message.textContent = 'Saved: ' + selected.textContent;
      updateProgress();
      if (carousel && currentIndex < cards.length - 1) {
        setTimeout(() => showCard(currentIndex + 1), 400);
      }
    } catch (error) { message.textContent = error.message; }
    finally { controls.forEach(control => { control.disabled = false; }); }
  });
});
