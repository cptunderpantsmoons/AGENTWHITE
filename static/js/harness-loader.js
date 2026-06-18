const HARNESS_STORAGE_KEY = 'carbon-agent-harness-enabled';
const HARNESS_CSS_ID = 'carbon-agent-harness-css';
const HARNESS_PARAM = 'harness';

function readHarnessPreference() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get(HARNESS_PARAM);

  if (requested === '1' || requested === 'true' || requested === 'on') {
    localStorage.setItem(HARNESS_STORAGE_KEY, 'true');
    return true;
  }

  if (requested === '0' || requested === 'false' || requested === 'off') {
    localStorage.removeItem(HARNESS_STORAGE_KEY);
    return false;
  }

  return localStorage.getItem(HARNESS_STORAGE_KEY) === 'true';
}

function loadHarnessStyles() {
  if (document.getElementById(HARNESS_CSS_ID)) return;
  const link = document.createElement('link');
  link.id = HARNESS_CSS_ID;
  link.rel = 'stylesheet';
  link.href = '/static/harness.css';
  document.head.appendChild(link);
}

function addHarnessExitPill() {
  if (document.getElementById('harness-exit-pill')) return;

  const pill = document.createElement('button');
  pill.id = 'harness-exit-pill';
  pill.type = 'button';
  pill.textContent = 'Layout ON';
  pill.title = 'Disable alternate layout';
  pill.setAttribute('aria-label', 'Disable alternate layout');
  pill.addEventListener('click', () => {
    localStorage.removeItem(HARNESS_STORAGE_KEY);
    const url = new URL(window.location.href);
    url.searchParams.set(HARNESS_PARAM, '0');
    window.location.replace(url.toString());
  });

  document.body.appendChild(pill);
}

async function enableHarness() {
  document.documentElement.classList.add('harness-enabled');
  document.body?.classList.add('harness-enabled');
  loadHarnessStyles();

  try {
    await import('/static/js/harness.js');
  } catch (error) {
    console.error('Alternate layout failed to load:', error);
  }

  addHarnessExitPill();
}

function stripHarnessParamIfDisabled() {
  const url = new URL(window.location.href);
  if (!url.searchParams.has(HARNESS_PARAM)) return;
  if (readHarnessPreference()) return;
  url.searchParams.delete(HARNESS_PARAM);
  window.history.replaceState({}, '', url.toString());
}

function bootHarnessLoader() {
  const enabled = readHarnessPreference();
  if (!enabled) {
    stripHarnessParamIfDisabled();
    return;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enableHarness, { once: true });
  } else {
    enableHarness();
  }
}

bootHarnessLoader();
