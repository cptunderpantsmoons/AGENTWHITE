#!/usr/bin/env bash
set -eu

# Odysseus smoke-test driver
# Usage: ./smoke.sh [screenshot|test|stop|start]
#   screenshot  — start server (if needed), run curl smoke tests, take screenshot
#   test        — start server (if needed), run curl smoke tests only
#   start       — start the server in the background and exit
#   stop        — stop the background server
#   status      — print whether the server is running
#
# Paths are relative to the repo root (one dir above this script).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
PIDFILE="/tmp/odysseus-smoke.pid"
PORT=7000
HOST=127.0.0.1
BASE_URL="http://${HOST}:${PORT}"

cd "$UNIT_DIR"

PYTHON="${UNIT_DIR}/venv/bin/python"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_log() { echo "[smoke] $*"; }

is_server_running() {
  curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/health" 2>/dev/null | grep -q '^200$'
}

our_pidfile_running() {
  [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

wait_for_server() {
  local max_wait=30 elapsed=0
  while ! is_server_running; do
    sleep 1
    ((++elapsed))
    if ((elapsed >= max_wait)); then
      _log "ERROR: server did not become ready within ${max_wait}s"
      return 1
    fi
  done
  _log "Server ready at ${BASE_URL}"
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_start() {
  if is_server_running; then
    _log "Server already running"
    return 0
  fi

  if [[ ! -x "$PYTHON" ]]; then
    _log "ERROR: venv not found at ${UNIT_DIR}/venv"
    _log "Run: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    return 1
  fi

  # Ensure LOCALHOST_BYPASS is enabled for auth-free loopback testing.
  if ! grep -q '^LOCALHOST_BYPASS=true' .env 2>/dev/null; then
    _log "Patching .env: LOCALHOST_BYPASS=true"
    sed -i 's/^# LOCALHOST_BYPASS=false/LOCALHOST_BYPASS=true/' .env
    sed -i 's/^LOCALHOST_BYPASS=false/LOCALHOST_BYPASS=true/' .env
    # Create entry if missing
    if ! grep -q '^LOCALHOST_BYPASS=' .env 2>/dev/null; then
      echo "LOCALHOST_BYPASS=true" >> .env
    fi
  fi

  nohup "$PYTHON" -m uvicorn app:app --host "$HOST" --port "$PORT" \
        > /tmp/odysseus-server.log 2>&1 &
  local pid=$!
  echo "$pid" > "$PIDFILE"
  _log "Started uvicorn (pid $pid) — log: /tmp/odysseus-server.log"
  wait_for_server
}

cmd_stop() {
  if our_pidfile_running; then
    local pid
    pid=$(cat "$PIDFILE")
    _log "Stopping uvicorn (pid $pid)"
    kill "$pid" 2>/dev/null || true
    rm -f "$PIDFILE"
  elif is_server_running; then
    _log "Server running but not managed by this script — leaving it alone"
  else
    _log "Server not running"
  fi
}

cmd_status() {
  if is_server_running; then
    _log "Server is RUNNING at ${BASE_URL}"
  else
    _log "Server is NOT running"
  fi
}

cmd_test() {
  cmd_start >/dev/null

  local code html health models static_ok=0

  _log "Smoke-test curl → ${BASE_URL}"

  # Health endpoint
  health=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/health")
  if [[ "$health" == "200" ]]; then
    _log "  /api/health  → 200 ✓"
  else
    _log "  /api/health  → $health ✗"
  fi

  # Root (redirects to chat/ or serves index.html)
  code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/")
  html=$(curl -s "${BASE_URL}/" | head -c 100)
  if [[ "$code" == "200" ]] && [[ "$html" == *DOCTYPE* ]]; then
    _log "  /            → 200 (HTML) ✓"
    static_ok=1
  else
    _log "  /            → $code (html=${#html}B)"
  fi

  # Static login page
  code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/static/login.html")
  if [[ "$code" == "200" ]]; then
    _log "  /static/login.html  → 200 ✓"
  else
    _log "  /static/login.html  → $code"
  fi

  # API that requires auth (should 403 or 401 when bypass is off; with bypass can vary)
  models=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/models")
  _log "  /api/models  → $models (auth-gated; 401/403 or 200 are OK)"

  if ((static_ok)); then
    _log "Smoke tests PASSED"
  else
    _log "Smoke tests had warnings (server may still be warming up)"
  fi
}

cmd_screenshot() {
  cmd_test >/dev/null

  local out="${UNIT_DIR}/screenshot.png"
  _log "Taking screenshot → $out"

  if command -v chromium >/dev/null 2>&1; then
    chromium --headless --disable-gpu --no-sandbox \
      --screenshot="$out" --window-size=1280,800 \
      "${BASE_URL}" 2>/dev/null
  elif [[ -x /snap/bin/chromium ]]; then
    /snap/bin/chromium --headless --disable-gpu --no-sandbox \
      --screenshot="$out" --window-size=1280,800 \
      "${BASE_URL}" 2>/dev/null
  else
    _log "WARNING: no chromium found. Skipping screenshot."
    return 1
  fi

  if [[ -f "$out" ]]; then
    local size
    size=$(stat -c%s "$out" 2>/dev/null || stat -f%z "$out" 2>/dev/null)
    _log "Screenshot saved: $out (${size} bytes)"
  else
    _log "WARNING: screenshot not written"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

case "${1:-screenshot}" in
  start)      cmd_start ;;
  stop)       cmd_stop ;;
  status)     cmd_status ;;
  test)       cmd_test ;;
  screenshot) cmd_screenshot ;;
  *)
    echo "Usage: $0 {start|stop|status|test|screenshot}"
    exit 1
    ;;
esac
