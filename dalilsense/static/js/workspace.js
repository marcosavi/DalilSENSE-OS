const presets = JSON.parse(document.getElementById('prompt-presets').textContent);
const modelSelect = document.getElementById('id_model');
const modelIcon = document.getElementById('selected-model-icon');
function updateModelIcon() {
  const isQwen = modelSelect.value.toLowerCase().split('/').pop().startsWith('qwen');
  modelIcon.hidden = !isQwen;
  modelSelect.parentElement.classList.toggle('has-model-icon', isQwen);
}
modelSelect.addEventListener('change', updateModelIcon);
updateModelIcon();
const promptPreset = document.getElementById('prompt-preset');
const promptInput = document.getElementById('id_system_prompt');
promptPreset.addEventListener('change', () => {
  if (presets[promptPreset.value]) promptInput.value = presets[promptPreset.value];
});
promptInput.addEventListener('input', () => { promptPreset.value = 'custom'; });
const selection = document.getElementById('id_selection');
function showSelection() {
  document.getElementById('count-field').hidden = selection.value === 'manual';
  document.getElementById('sample-field').hidden = selection.value !== 'random';
  document.getElementById('cases-field').hidden = selection.value !== 'manual';
}
selection.addEventListener('change', showSelection);
showSelection();
document.getElementById('configuration').addEventListener('submit', event => {
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = 'Starting experiment…';
});
// Restore the submit control when returning through the browser's back cache.
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
