const disclosures = document.querySelectorAll('.header-disclosure');
disclosures.forEach(detail => detail.addEventListener('toggle', () => {
  if (detail.open) {
    disclosures.forEach(other => { if (other !== detail) other.open = false; });
    if (detail.id === 'case-search') document.getElementById('case-query').focus();
  }
}));
document.addEventListener('click', event => {
  disclosures.forEach(detail => { if (!detail.contains(event.target)) detail.open = false; });
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') disclosures.forEach(detail => {
    if (detail.open) { detail.open = false; detail.querySelector('summary').focus(); }
  });
});
