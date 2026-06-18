const HARNESS_CHIPS = [
  { id: 'harness-chip-mode', label: 'Mode', read: () => document.querySelector('#mode-agent-btn.active') ? 'Agent' : 'Chat' },
  { id: 'harness-chip-model', label: 'Model', read: () => document.querySelector('#model-picker-label')?.textContent?.trim() || 'Select' },
  { id: 'harness-chip-tools', label: 'Tools', read: activeTools },
];

function activeTools() {
  const tools = [
    ['#web-toggle-btn[aria-pressed="true"], #web-toggle:checked', 'Web'],
    ['#bash-toggle-btn[aria-pressed="true"], #bash-toggle:checked', 'Shell'],
    ['#plan-toggle-btn[aria-pressed="true"], #plan-toggle:checked', 'Plan'],
    ['#rag-toggle:checked', 'RAG'],
    ['#research-toggle:checked', 'Research'],
  ];
  const active = tools.filter(([selector]) => document.querySelector(selector)).map(([, name]) => name);
  return active.length ? active.join(' · ') : 'Standby';
}

function createStatusStrip() {
  if (document.querySelector('.harness-status-strip')) return;
  const strip = document.createElement('div');
  strip.className = 'harness-status-strip';
  strip.setAttribute('aria-hidden', 'true');

  for (const chip of HARNESS_CHIPS) {
    const node = document.createElement('div');
    node.className = 'harness-chip';
    node.id = chip.id;
    strip.appendChild(node);
  }

  document.body.appendChild(strip);
  refreshStatusStrip();
}

function refreshStatusStrip() {
  for (const chip of HARNESS_CHIPS) {
    const node = document.getElementById(chip.id);
    if (!node) continue;
    const value = chip.read();
    const next = `${chip.label}: <strong>${escapeHtml(value)}</strong>`;
    if (node.dataset.rendered === next) continue;
    node.dataset.rendered = next;
    node.innerHTML = next;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function watchHarnessState() {
  let pending = false;
  const scheduleRefresh = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      refreshStatusStrip();
    });
  };

  const observer = new MutationObserver((mutations) => {
    if (mutations.every((mutation) => mutation.target.closest?.('.harness-status-strip'))) return;
    scheduleRefresh();
  });
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class', 'aria-pressed', 'style'],
  });

  document.addEventListener('click', scheduleRefresh, true);
  document.addEventListener('input', scheduleRefresh, true);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    createStatusStrip();
    watchHarnessState();
  }, { once: true });
} else {
  createStatusStrip();
  watchHarnessState();
}
