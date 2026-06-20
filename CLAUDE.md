# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CarbonAgent  is a self-hosted AI workspace — a FastAPI backend with a vanilla-JS frontend. It provides chat, agentic tool execution, memory, deep research, documents, email/calendar, notes/tasks, and a Cookbook subsystem for serving local models.

## Development Commands

### First-time setup

```bash
cp .env.example .env
```

Then choose one path:

**Docker (recommended)**

```bash
docker compose up -d --build
# App at http://localhost:7000
```

**Native Linux/macOS**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python setup.py
python -m uvicorn app:app --host 127.0.0.1 --port 7000
```

**macOS with `start-macos.sh`** (Metal GPU, port 7860 by default because AirPlay often holds 7000):

```bash
./start-macos.sh
```

`setup.py` creates `data/` directories, initializes the SQLite database, generates an admin password, and copies `.env.example` to `.env` if missing.

### Running tests and checks

Run the full Python test suite:

```bash
python -m pytest
```

Run a single test file:

```bash
python -m pytest tests/test_something.py -v
```

Run the small JS + README check defined in `package.json`:

```bash
npm test
# Equivalent to: python3 -m pytest tests/test_readme_ascii_fenced.py -q && node --check static/js/theme.js
```

Run the Python syntax check used in CI:

```bash
python -m compileall -q app.py core routes src services scripts tests
```

Syntax-check a changed JS file:

```bash
node --check static/js/<file>.js
```

Validate Compose config after edits:

```bash
docker compose config
```

### Useful runtime commands

```bash
docker compose ps
docker compose logs --tail=120 app
docker compose logs app | grep -E 'ChromaDB|MemoryVectorStore|DEGRADED'
```

## High-Level Architecture

### Backend

`app.py` is the FastAPI entry point. It wires CORS, request-timeout middleware, auth, static files, and route modules. Use the lifespan context manager for startup/shutdown logic rather than deprecated `@app.on_event` decorators.

| Layer | Purpose |
|-------|---------|
| `core/` | Foundation: `database.py` (SQLAlchemy models/engine), `auth.py` (bcrypt sessions + users in `data/auth.json`), `middleware.py` (`SecurityHeadersMiddleware`, `require_admin`, internal-tool token), `constants.py` (paths + env helpers) |
| `routes/` | FastAPI route modules grouped by feature: chat, auth, documents, memory, calendar, email, cookbook, research, etc. |
| `src/` | Business logic consumed by routes: LLM calling, agent loop, tool execution, MCP management, memory/search providers, Cookbook lifecycle, RAG, research pipeline, white-label config |
| `services/` | Supporting service integrations |
| `scripts/` | CLI helpers, diagnostics, and Cookbook server wrappers |

### Frontend

`static/` holds the single-page UI: `index.html`, `app.js`, `style.css`, plus modular JS under `static/js/`. The frontend consumes the REST API and renders streamed responses. There is no build step; files are served as static assets.

### Agent loop

`src/agent_loop.py` drives multi-turn tool execution around `src/llm_core.py`'s streaming LLM calls. The LLM emits tools as fenced code blocks; `src/tool_parsing.py` scans the stream incrementally and `src/agent_tools.py` / `src/tool_implementations.py` execute them. Available tools include built-ins (bash, Python, file I/O, search, documents, notes, calendar, email, etc.), MCP servers managed by `src/mcp_manager.py`, and provider-defined tools from memory providers.

### Memory

`src/memory_provider.py` defines the `MemoryProvider` interface. The default `NativeMemoryProvider` writes to `data/memory.json` and uses ChromaDB/fastembed-backed vectors when available; it degrades to keyword fallback if vector dependencies are missing.

### Cookbook

The Cookbook subsystem (`routes/cookbook_routes.py`, `routes/cookbook_helpers.py`, `src/cookbook_serve_lifecycle.py`) manages model downloads and serve processes, typically inside `tmux` sessions. It tracks state in `data/cookbook_state.json`. GPU passthrough is controlled by Docker Compose overlays (`docker/gpu.nvidia.yml`, `docker/gpu.amd.yml`); the base image is CPU-only and CUDA/ROCm userspace must be installed through Cookbook -> Dependencies.

### Deep research

`src/deep_research.py` and `src/research_handler.py` run multi-step web research, producing visual reports via `src/visual_report.py`. Research jobs are long-running and exempt from the global request timeout.

### White-label / branding

`src/white_label.py` is the single source of truth for all brand-facing strings, colors, and header names. It reads `WL_*` env vars with `ODYSSEUS_*` legacy fallbacks. Do not hardcode product names or brand colors elsewhere; import from `src.white_label`.

## Authentication and Privilege Model

`core/auth.py` persists users in `data/auth.json` and session tokens in `data/sessions.json`. The first boot creates an admin user whose temporary password is printed to the terminal.

- `core.middleware.require_admin` gates admin-only routes.
- The in-process agent tool loop routes through an internal token (`INTERNAL_TOOL_TOKEN` / `X-App-Internal-Token`) so tools can call admin-gated endpoints on behalf of the user.
- `LOCALHOST_BYPASS=true` bypasses auth for loopback requests; keep it `false` outside local development.
- Reserved usernames (`internal-tool`, `api`, `demo`, `system`) are forbidden because the code uses them as synthetic owner sentinels.

## Environment and Configuration

Runtime configuration lives in `.env` (copied from `.env.example`). Key variables:

- `LLM_HOST`, `LLM_HOSTS`, `OPENAI_API_KEY` — LLM providers
- `SEARXNG_INSTANCE` — web search; Docker overrides to `http://searxng:8080`
- `DATABASE_URL` — defaults to `sqlite:///./data/app.db`
- `CHROMADB_HOST`, `CHROMADB_PORT` — vector memory; Docker overrides to `chromadb:8000`
- `AUTH_ENABLED`, `LOCALHOST_BYPASS`, `SECURE_COOKIES`
- `APP_BIND`, `APP_PORT` — Docker Compose host bind
- `WL_*` / `ODYSSEUS_*` — branding, admin credentials, feature toggles

The `.env.example` contains inline documentation for each variable.

## Data Layout

All mutable runtime state lives under `data/` and is gitignored:

- `data/app.db` — SQLite database (sessions, messages, documents, etc.)
- `data/auth.json`, `data/sessions.json` — auth state
- `data/memory.json`, `data/memory_vectors/` — memory
- `data/uploads/`, `data/personal_docs/`, `data/generated_images/` — user content
- `data/cookbook_state.json` — Cookbook state
- `data/huggingface/`, `data/local/`, `data/ssh/` — Cookbook caches and keys in Docker

## Contribution Conventions

Read `CONTRIBUTING.md` for the full guide. Highlights:

- Open PRs against **`dev`**, not `main`.
- Keep PRs small and focused; do not mix unrelated refactors, formatting, and behavior changes.
- For any UI change, run the app locally and attach screenshots (including mobile when relevant).
- Reuse existing CSS variables and component classes in `static/`; do not introduce new color values, font sizes, spacing units, or Unicode emoji. Use inline SVG matching the monochrome icon style.
- Dark theme is the default; light-mode work goes through the existing theme system.
- Run `git diff --check`, `python -m py_compile` on changed files, and focused `pytest` before submitting.

## CI

`.github/workflows/ci.yml` runs three jobs:

1. `python -m compileall -q app.py core routes src services scripts tests`
2. `node --check` on `static/app.js` and `static/js/**/*.js`
3. `python -m pytest -q` (informational / continue-on-error for now)

## Important Safety Constraints

- CarbonAgent is an admin console with shell access, file uploads, API tokens, and model execution. Prefer binding to `127.0.0.1`; expose to LAN/reverse proxy intentionally and with auth enabled.
- Never commit `.env`, `data/`, `logs/`, credentials, or generated media.
- Keep `AUTH_ENABLED=true` and `LOCALHOST_BYPASS=false` for any network-accessible deployment.
