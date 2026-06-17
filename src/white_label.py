# src/white_label.py
"""White-label configuration — all brand-facing strings in one source of truth.

Every module in the project reads brand strings through this module, never
hardcodes them. Environment variables prefixed with ``WL_`` take highest
priority; legacy ``ODYSSEUS_*`` variables are read as fallbacks so existing
deployments continue to work without changes.

Usage::

    from src.white_label import WL

    print(WL.APP_NAME)
    print(WL.header("Event"))
    print(WL.internal_header("Origin"))
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _env(key: str, default: str, *, legacy: Optional[str] = None) -> str:
    """Resolve ``WL_<key>`` first, fall back to ``ODYSSEUS_<legacy>``, then *default*."""
    wl = os.getenv(f"WL_{key}")
    if wl is not None:
        return wl
    if legacy is not None:
        legacy_val = os.getenv(legacy)
        if legacy_val is not None:
            logger.debug("Using legacy env var %s (set WL_%s to silence this)", legacy, key)
            return legacy_val
    return default


def _env_bool(key: str, default: bool, *, legacy: Optional[str] = None) -> bool:
    raw = _env(key, str(default), legacy=legacy)
    return raw.strip().lower() in ("1", "true", "yes")


def _env_int(key: str, default: int, *, legacy: Optional[str] = None) -> int:
    raw = _env(key, str(default), legacy=legacy)
    try:
        return int(raw)
    except ValueError:
        return default


# ===================================================================
# Product identity
# ===================================================================

APP_NAME: str = _env("APP_NAME", "CarbonAgent", legacy="ODYSSEUS_APP_NAME")
"""Full application name shown in page titles, headers, and metadata."""

APP_SHORT_NAME: str = _env("APP_SHORT_NAME", "CarbonAgent", legacy="ODYSSEUS_APP_SHORT_NAME")
"""Short name for PWA manifest and constrained UI slots."""

APP_DESCRIPTION: str = _env(
    "APP_DESCRIPTION",
    "CarbonAgent — AI workspace for chat, memory, research, and tools",
    legacy="ODYSSEUS_APP_DESCRIPTION",
)
"""Tagline / description used in meta tags and PWA manifest."""

APP_LEGAL_FOOTER: str = _env("APP_LEGAL_FOOTER", "", legacy="ODYSSEUS_LEGAL_FOOTER")
"""Optional legal or attribution footer text (e.g. "Powered by …")."""

APP_LOGO_TEXT: str = _env("APP_LOGO_TEXT", "CarbonAgent", legacy="ODYSSEUS_APP_LOGO_TEXT")
"""Text rendered as the wordmark on the login page and loading screen."""

APP_VERSION: str = _env("APP_VERSION", "1.0.0")
"""Release version string. May be overridden at deploy time."""

APP_THEME_COLOR: str = _env("APP_THEME_COLOR", "#0A0A0A", legacy="ODYSSEUS_THEME_COLOR")
"""Browser theme-color meta tag value."""

APP_FAVICON_SVG: str = _env("APP_FAVICON_SVG", "", legacy="ODYSSEUS_FAVICON_SVG")
"""Custom favicon SVG data URI (inline). Empty = use default neutral icon."""

# ===================================================================
# Brand / visual identity tokens
# ===================================================================

BRAND_COLOR: str = _env("BRAND_COLOR", "#C61A1D", legacy="ODYSSEUS_BRAND_COLOR")
"""Default accent / brand colour (Corporate Carbon red)."""

LOGO_LIGHT_URL: str = _env("LOGO_LIGHT_URL", "/static/brand/logo.svg", legacy="ODYSSEUS_LOGO_LIGHT_URL")
"""URL for light-mode brand logo (SVG preferred)."""

LOGO_DARK_URL: str = _env("LOGO_DARK_URL", "/static/brand/logo-dark.svg", legacy="ODYSSEUS_LOGO_DARK_URL")
"""URL for dark-mode brand logo; fallback to LOGO_LIGHT_URL if absent."""

LOGO_HEIGHT: str = _env("LOGO_HEIGHT", "32px", legacy="ODYSSEUS_LOGO_HEIGHT")
"""CSS value for brand logo height."""

# ===================================================================
# HTTP header naming
# ===================================================================

HEADER_PREFIX: str = _env("HEADER_PREFIX", "X-App-", legacy="ODYSSEUS_HEADER_PREFIX")
"""Prefix for application-internal HTTP headers."""

INTERNAL_HEADER_PREFIX: str = _env(
    "INTERNAL_HEADER_PREFIX", "X-App-Internal-", legacy="ODYSSEUS_INTERNAL_HEADER_PREFIX"
)
"""Prefix for strictly-internal HTTP headers (routing, origin tracking)."""


def header(name: str) -> str:
    """Return a full header name for the given *name*.

    Example::

        header("Event")        -> "X-App-Event"
        header("Signature")    -> "X-App-Signature"
    """
    return f"{HEADER_PREFIX}{name}"


def internal_header(name: str) -> str:
    """Return a full internal-header name.

    Example::

        internal_header("Origin")   -> "X-App-Internal-Origin"
        internal_header("Kind")     -> "X-App-Internal-Kind"
    """
    return f"{INTERNAL_HEADER_PREFIX}{name}"


# ===================================================================
# CalDAV / iCal identifiers
# ===================================================================

ICAL_PRODID: str = _env("ICAL_PRODID", "-//App//Calendar//EN", legacy="ODYSSEUS_ICAL_PRODID")
"""PRODID value in generated iCalendar (.ics) exports."""

CALDAV_PRODID: str = _env("CALDAV_PRODID", "-//App//CalDAV//EN", legacy="ODYSSEUS_CALDAV_PRODID")
"""PRODID value for CalDAV write-back entries."""

# ===================================================================
# User-agent strings
# ===================================================================

USER_AGENT: str = _env("USER_AGENT", "CarbonAgent/1.0", legacy="ODYSSEUS_USER_AGENT")
"""User-Agent header sent in outbound HTTP requests from webhooks."""

COPILOT_USER_AGENT: str = _env(
    "COPILOT_USER_AGENT", "CarbonAgent/1.0", legacy="ODYSSEUS_COPILOT_USER_AGENT"
)
"""User-Agent for GitHub Copilot API integration."""

COPILOT_EDITOR_VERSION: str = _env(
    "COPILOT_EDITOR_VERSION", "CarbonAgent/1.0", legacy="ODYSSEUS_COPILOT_EDITOR_VERSION"
)
"""Editor-version string for GitHub Copilot API."""

# ===================================================================
# Admin / setup
# ===================================================================

ADMIN_USER_VAR: str = "WL_ADMIN_USER"
"""Env-var name for pre-seeding the admin username."""

ADMIN_PASSWORD_VAR: str = "WL_ADMIN_PASSWORD"
"""Env-var name for pre-seeding the admin password."""

ADMIN_USER: str = _env("ADMIN_USER", "admin", legacy="ODYSSEUS_ADMIN_USER")
"""Default admin username."""

# ===================================================================
# Internal routing / placeholders
# ===================================================================

MAIL_ORIGIN: str = _env("MAIL_ORIGIN", "app-ui", legacy="ODYSSEUS_MAIL_ORIGIN")
"""Value for the origin header on internally-generated email messages."""


def default_chat_name() -> str:
    """Return the default "new chat" placeholder name."""
    return f"{APP_SHORT_NAME} Chat"


def default_page_title(section: str = "") -> str:
    """Return a page-title string, optionally with a section.

    Examples::

        default_page_title()              -> ""
        default_page_title("Calendar")    -> "Calendar — "
    """
    if section:
        return f"{section} — {APP_NAME}"
    return APP_NAME


def research_report_header() -> str:
    """Header text for deep-research visual reports."""
    return f"{APP_NAME} — Deep Research Report"


def research_report_footer(timestamp: str) -> str:
    """Footer text for deep-research visual reports, incl. *timestamp*."""
    return f"Generated by {APP_NAME} • {timestamp}",