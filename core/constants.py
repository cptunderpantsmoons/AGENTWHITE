# core/constants.py
"""Application-wide constants and configuration values."""
import os

import src.white_label as wl

APP_VERSION = wl.APP_VERSION

# Base paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/"
STATIC_DIR = os.path.join(BASE_DIR, "static")
# Allow the Electron / portable launcher to relocate the writable data
# directory (e.g. next to the executable on a USB drive).
DATA_DIR = os.path.abspath(os.getenv("ODYSSEUS_DATA_DIR") or os.path.join(BASE_DIR, "data"))

# Data file paths
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")
MEMORY_DOC = os.path.join(DATA_DIR, "memory_doc.md")
PERSONAL_DIR = os.path.join(DATA_DIR, "personal_docs")
RUNBOOK_DIR = os.path.join(PERSONAL_DIR, "runbook")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
FEATURES_FILE = os.path.join(DATA_DIR, "features.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# API Configuration
MAX_CONTEXT_MESSAGES = 90
REQUEST_TIMEOUT = 20
OPENAI_COMPAT_PATH = "/v1/chat/completions"

# Environment variables with defaults
DEFAULT_HOST = os.getenv("LLM_HOST", "localhost")
LLM_HOSTS = [h.strip() for h in os.getenv("LLM_HOSTS", "").split(",") if h.strip()]
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SEARXNG_INSTANCE = os.getenv('SEARXNG_INSTANCE', 'http://localhost:8080')


def _env(name: str, default: str = "", legacy: str | None = None) -> str:
    val = os.getenv(name)
    if val is None and legacy:
        val = os.getenv(legacy, default)
    return val if val is not None else default


def _env_int(name: str, default: int = 0, legacy: str | None = None) -> int:
    return int(_env(name, str(default), legacy=legacy))


# Cleanup configuration
CLEANUP_ENABLED = _env("CLEANUP_ENABLED", "True", legacy="CLEANUP_ENABLED").lower() == "true"
CLEANUP_INTERVAL_HOURS = _env_int("CLEANUP_INTERVAL_HOURS", 24, legacy="CLEANUP_INTERVAL_HOURS")

# Default parameters
DEFAULT_TEMPERATURE = 1.0
DEFAULT_MAX_TOKENS = 0
