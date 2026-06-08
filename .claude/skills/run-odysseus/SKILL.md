---
name: run-odysseus
description: |
  Run, smoke-test, and screenshot the Odysseus AI Workspace web app.
  Start the FastAPI/uvicorn server, drive it with curl + headless chromium,
  and take screenshots. Also covers dependency setup and the venv path.
---

# Odysseus — Web App Smoke & Screenshot Driver

Odysseus is a self-hosted AI workspace: a FastAPI backend (`app.py`) serving a
static HTML/JS frontend (`static/`). The agent-facing driver is a bash script
that starts the server, runs curl smoke tests, and snaps a screenshot with
headless Chromium.

**Paths in this doc are relative to the repo root** (`odysseus/`).

## Prerequisites

Verified on this Ubuntu container:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip curl
```

A headless Chromium is needed for screenshots. On Ubuntu we used the snap:

```bash
/snap/bin/chromium --version   # should print a version
```

If you only have Playwright-installed Chromium, that works too — the driver
falls back to `chromium` in `$PATH`.

## Build

1. Create the Python venv and install deps:

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

2. Copy the example environment (safe defaults, no secrets needed):

```bash
cp .env.example .env
```

3. Run first-time setup (creates `data/` dirs, SQLite DB, and `data/auth.json`):

```bash
ODYSSEUS_SKIP_ADMIN_PROMPT=1 ODYSSEUS_ADMIN_USER=admin ODYSSEUS_ADMIN_PASSWORD=admin123 ./venv/bin/python setup.py
```

## Run (agent path)

The driver lives at:

```
.claude/skills/run-odysseus/smoke.sh
```

Make it executable once:

```bash
chmod +x .claude/skills/run-odysseus/smoke.sh
```

### Commands

| Command | What it does |
|---------|-------------|
| `start` | Starts uvicorn on `127.0.0.1:7000` in the background, patches `.env` with `LOCALHOST_BYPASS=true` for auth-free loopback testing, and waits for `/api/health` to return 200. |
| `stop`  | Stops the uvicorn process managed by the script. |
| `status`| Prints whether the server is responding. |
| `test`  | Starts server if needed, then curls `/api/health`, `/`, `/static/login.html`, and `/api/models`. |
| `screenshot` | Runs `test`, then opens the app in headless Chromium (`--window-size=1280,800`) and writes `screenshot.png` in the repo root. |

### Typical flow

```bash
# Start the server
./.claude/skills/run-odysseus/smoke.sh start

# Run smoke tests
./.claude/skills/run-odysseus/smoke.sh test

# Take a screenshot
./.claude/skills/run-odysseus/smoke.sh screenshot
# → writes ./screenshot.png
```

Server logs land at `/tmp/odysseus-server.log`.

## Direct invocation (no full server)

For PRs that only touch internal Python code, you can import and run without
the full app:

```bash
source venv/bin/activate
python -c "from src.tool_schemas import TOOL_SCHEMAS; print(list(TOOL_SCHEMAS.keys()))"
```

Or run the pytest suite:

```bash
venv/bin/pytest -x -q
```

## Run (human path)

For interactive local use (opens in your browser, requires login):

```bash
source venv/bin/activate
python -m uvicorn app:app --host 127.0.0.1 --port 7000
# open http://127.0.0.1:7000
```

Login with the admin credentials from `setup.py` (or read the temporary
password printed at first boot).

## Gotchas

- **Auth bypass only works on loopback.** `LOCALHOST_BYPASS=true` in `.env`
  bypasses login for requests from `127.0.0.1`. This is how the smoke test
  accesses the app without credentials. Do not set this on a LAN-facing
  deployment.

- **Snap Chromium sandbox.** On Ubuntu systems with snap Chromium,
  `--no-sandbox` is passed automatically so headless screenshots work inside
  containers. On systems with a regular Chromium install, `--no-sandbox` is not
  needed but is harmless.

- **`data/auth.json` is sticky.** If it exists, `setup.py` skips admin creation.
  To reset auth (e.g. after setting `ODYSSEUS_ADMIN_PASSWORD`), delete
  `data/auth.json` and rerun `setup.py`.

- **ChromaDB is optional for a basic run.** The app starts fine without ChromaDB;
  vector memory and RAG routes degrade gracefully with log warnings. If you want
  the full stack, use `docker compose up -d chromadb`.

- **Port 7000 default.** `APP_PORT` in `.env` can override this. The smoke script
  hardcodes `7000`; if you change `.env`, update `PORT` in `smoke.sh` too.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `venv not found` | Run `python3 -m venv venv && venv/bin/pip install -r requirements.txt` |
| Server starts but `/api/health` never returns 200 | Check `/tmp/odysseus-server.log` for import errors, missing deps, or port conflicts (`lsof -i :7000`) |
| Screenshot fails with `no chromium found` | Install a headless Chromium: `sudo snap install chromium`, or `playwright install chromium` |
| Static files 404 | Ensure you are running from the repo root (where `static/` exists); uvicorn serves `app:app` which mounts `static/` |
| `auth.json already exists` but login fails | Delete `data/auth.json` and rerun `setup.py` with desired admin credentials |
| Front-end shows a blank dark page in screenshot | The SPA loads its JS asynchronously; give it a moment. The screenshot may show the loading shell before the UI fully renders. This is normal for a quick headless snap — the server is still healthy. |
