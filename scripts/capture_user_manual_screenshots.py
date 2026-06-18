from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:7000/"
OUT = Path("docs/user-manual-assets")
OUT.mkdir(parents=True, exist_ok=True)

DESKTOP = {"width": 1440, "height": 1000}
MOBILE = {"width": 390, "height": 844}


def safe_click(page, selector, timeout=2500):
    try:
        loc = page.locator(selector).first
        loc.wait_for(state="attached", timeout=timeout)
        loc.click(timeout=timeout, force=True)
        page.wait_for_timeout(700)
        return True
    except Exception as exc:
        print(f"WARN click failed {selector}: {exc}")
        return False


def close_popups(page):
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    for sel in [
        "#close-memory-modal",
        "#close-theme-popup",
        "#close-custom-preset",
        "#close-cookbook-modal",
        ".modal:not(.hidden) .close-btn",
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(force=True, timeout=600)
                page.wait_for_timeout(150)
        except Exception:
            pass


def stabilize(page):
    close_popups(page)
    try:
        page.evaluate(
            """
            () => {
              document.querySelectorAll('.loading-screen,.toast,.tooltip,.tour-hint,.tour-popover')
                .forEach(e => e.remove());
              document.body.classList.remove('sidebar-collapsed');
            }
            """
        )
    except Exception:
        pass


def shot(page, name, title=""):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"SHOT {name}: {title} -> {path}")


def goto_app(page, suffix="?harness=0"):
    page.goto(BASE_URL + suffix, wait_until="commit", timeout=15000)
    page.wait_for_timeout(4200)
    stabilize(page)


def open_tool(page, selector):
    close_popups(page)
    safe_click(page, selector)
    page.wait_for_timeout(1000)


def capture_core(page):
    goto_app(page, "?harness=0&manual=core")
    shot(page, "01-chat-workspace", "Default chat workspace")

    safe_click(page, "#model-picker-btn")
    shot(page, "02-model-picker", "Model picker")
    close_popups(page)

    try:
        page.fill("#message", "Draft a project plan for reducing cloud costs")
    except Exception:
        pass
    for sel in ["#web-toggle-btn", "#bash-toggle-btn", "#plan-toggle-btn"]:
        safe_click(page, sel, timeout=1200)
    shot(page, "03-agent-tools", "Agent/chat tool toggles")

    safe_click(page, "#overflow-plus-btn")
    shot(page, "04-overflow-tools", "Overflow tools")

    safe_click(page, "#overflow-preset-btn")
    page.wait_for_timeout(700)
    shot(page, "05-prompt-inject", "Prompt inject controls")
    if safe_click(page, '[data-chartab="character"]'):
        shot(page, "06-persona", "Persona controls")
    if safe_click(page, '[data-chartab="group"]'):
        shot(page, "07-group-chat", "Group chat controls")
    close_popups(page)

    safe_click(page, "#sidebar-search-btn")
    shot(page, "08-conversation-search", "Conversation search")
    close_popups(page)


def capture_tools(page):
    tools = [
        ("#tool-memory-btn", "09-brain-memory", "Brain memories"),
        ("#tool-calendar-btn", "12-calendar", "Calendar"),
        ("#tool-compare-btn", "13-compare", "Compare"),
        ("#tool-cookbook-btn", "14-cookbook-download", "Cookbook download"),
        ("#tool-research-btn", "18-deep-research", "Deep Research"),
        ("#tool-gallery-btn", "19-gallery", "Gallery"),
        ("#tool-library-btn", "20-library-documents", "Library documents"),
        ("#tool-notes-btn", "21-notes", "Notes"),
        ("#tool-tasks-btn", "22-tasks", "Tasks"),
        ("#tool-theme-btn", "23-theme-browse", "Theme browser"),
    ]
    for selector, filename, label in tools:
        open_tool(page, selector)
        shot(page, filename, label)
        if filename == "09-brain-memory":
            if safe_click(page, '[data-memory-tab="skills"]'):
                shot(page, "10-brain-skills", "Brain skills")
            if safe_click(page, '[data-memory-tab="add"]'):
                shot(page, "11-brain-add", "Add memory or skill")
        if filename == "14-cookbook-download":
            for text, fname, title in [
                ("Serve", "15-cookbook-serve", "Cookbook serve"),
                ("Dependencies", "16-cookbook-dependencies", "Cookbook dependencies"),
                ("Settings", "17-cookbook-settings", "Cookbook settings"),
            ]:
                try:
                    page.locator('#cookbook-modal .cookbook-tab').filter(has_text=text).first.click(timeout=1500, force=True)
                    page.wait_for_timeout(800)
                    shot(page, fname, title)
                except Exception as exc:
                    print(f"WARN cookbook tab {text}: {exc}")
        if filename == "23-theme-browse":
            if safe_click(page, '[data-tab="theme-tab-customize"]'):
                shot(page, "24-theme-customize", "Theme customization")


def capture_settings(page):
    close_popups(page)
    safe_click(page, "#user-bar-settings")
    page.wait_for_timeout(800)
    shot(page, "25-settings-add-models", "Settings: add models")
    for tab, fname, title in [
        ("ai", "26-settings-ai-defaults", "Settings: AI defaults"),
        ("search", "27-settings-search", "Settings: search"),
        ("integrations", "28-settings-integrations", "Settings: integrations"),
        ("email", "29-settings-email", "Settings: email"),
        ("appearance", "30-settings-appearance", "Settings: appearance"),
        ("shortcuts", "31-settings-shortcuts", "Settings: shortcuts"),
        ("account", "32-settings-account", "Settings: account"),
    ]:
        if safe_click(page, f'[data-settings-tab="{tab}"]'):
            shot(page, fname, title)
    close_popups(page)

    if safe_click(page, "#email-section-title", timeout=1000) or safe_click(page, "#rail-email", timeout=1000):
        shot(page, "33-email", "Email")
    close_popups(page)


def capture_harness(page):
    goto_app(page, "?harness=1&manual=harness")
    shot(page, "34-layout-mode-workspace", "Alternate layout workspace")

    try:
        page.fill("#message", "Create a launch checklist for a model evaluation run")
    except Exception:
        pass
    for sel in ["#web-toggle-btn", "#plan-toggle-btn"]:
        safe_click(page, sel, timeout=1200)
    shot(page, "35-layout-mode-command-deck", "Alternate layout command deck")

    open_tool(page, "#tool-cookbook-btn")
    shot(page, "36-layout-mode-cookbook", "Alternate layout with Cookbook")
    close_popups(page)

    safe_click(page, "#user-bar-settings")
    page.wait_for_timeout(800)
    shot(page, "37-layout-mode-settings", "Alternate layout with Settings")
    close_popups(page)


def capture_mobile(browser):
    context = browser.new_context(viewport=MOBILE, device_scale_factor=2, is_mobile=True)
    page = context.new_page()
    goto_app(page, "?harness=0&manual=mobile")
    shot(page, "38-mobile-workspace", "Mobile workspace")
    if not safe_click(page, "#mobile-menu-btn"):
        try:
            page.evaluate("document.getElementById('mobile-menu-btn')?.click()")
        except Exception:
            pass
    page.wait_for_timeout(700)
    shot(page, "39-mobile-navigation", "Mobile navigation")
    context.close()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path="/snap/bin/chromium")
        context = browser.new_context(viewport=DESKTOP, device_scale_factor=1)
        page = context.new_page()
        capture_core(page)
        capture_tools(page)
        capture_settings(page)
        capture_harness(page)
        context.close()
        capture_mobile(browser)
        browser.close()


if __name__ == "__main__":
    main()
