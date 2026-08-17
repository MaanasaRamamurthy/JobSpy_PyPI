from __future__ import annotations

import argparse
from pathlib import Path

import requests
from playwright.sync_api import BrowserContext, Page, sync_playwright

from jobspy.naukri.config import (
    AUTH_CHECK_URL,
    BROWSER,
    BROWSER_CHANNEL,
    LOGIN_URL,
    SESSION_BOOTSTRAP_URL,
    STORAGE_STATE_PATH,
)
from jobspy.naukri.constant import headers


class NaukriAuthenticationError(RuntimeError):
    """Raised when a usable authenticated Naukri session is unavailable."""


def create_naukri_login_state(
    storage_state_path: Path = STORAGE_STATE_PATH,
    timeout_ms: int = 120000,
) -> Path:
    """Open an interactive browser and persist the completed Naukri login."""
    storage_state_path = Path(storage_state_path)
    storage_state_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = _launch_browser(playwright, headless=False)
        context = _new_context(browser)
        page = context.new_page()

        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            print(
                "\nComplete the Naukri login in the browser, including any OTP or "
                "CAPTCHA.\nAfter your account homepage is visible, return here and "
                "press Enter."
            )
            input()

            if not _is_authenticated(page, timeout_ms):
                raise NaukriAuthenticationError(
                    "Naukri login could not be verified. Complete login in the browser "
                    "before pressing Enter."
                )

            context.storage_state(path=str(storage_state_path))
        finally:
            context.close()
            browser.close()

    return storage_state_path


def setup_naukri_session(
    session: requests.Session,
    timeout_ms: int = 60000,
) -> tuple[requests.Session, dict[str, str]]:
    """Populate a requests session from an authenticated Naukri browser session."""
    if not STORAGE_STATE_PATH.is_file():
        raise NaukriAuthenticationError(
            "Naukri authentication state is missing. Run "
            "'python -m jobspy.naukri.session --login' first."
        )

    captured_headers: dict[str, str] = {}

    with sync_playwright() as playwright:
        browser = _launch_browser(playwright, headless=True)
        context = _new_context(browser, STORAGE_STATE_PATH)
        page = context.new_page()

        def capture_request(request):
            if "jobapi/v3/search" in request.url and "nkparam" in request.headers:
                captured_headers["nkparam"] = request.headers["nkparam"]

        page.on("request", capture_request)

        try:
            if not _is_authenticated(page, timeout_ms):
                raise NaukriAuthenticationError(
                    "Saved Naukri authentication has expired. Run "
                    "'python -m jobspy.naukri.session --login' again."
                )

            page.goto(
                SESSION_BOOTSTRAP_URL,
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )
            for _ in range(15):
                if "nkparam" in captured_headers:
                    break
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)

            if "nkparam" not in captured_headers:
                raise NaukriAuthenticationError(
                    "Naukri did not issue an nkparam search token. The browser "
                    "bootstrap flow may have changed."
                )

            playwright_cookies = context.cookies()
        finally:
            context.close()
            browser.close()

    for cookie in playwright_cookies:
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain"),
            path=cookie.get("path", "/"),
        )

    return session, captured_headers


def _launch_browser(playwright, headless: bool):
    if BROWSER == "chromium":
        launch_options = {"headless": headless}
        if BROWSER_CHANNEL:
            launch_options["channel"] = BROWSER_CHANNEL
        return playwright.chromium.launch(**launch_options)

    if BROWSER == "firefox":
        return playwright.firefox.launch(headless=headless)

    raise ValueError(
        f"Unsupported NAUKRI_BROWSER={BROWSER!r}. Use 'chromium' or 'firefox'."
    )


def _new_context(browser, storage_state_path: Path | None = None) -> BrowserContext:
    options = {
        "user_agent": headers["user-agent"],
        "viewport": {"width": 1920, "height": 1080},
    }
    if storage_state_path is not None:
        options["storage_state"] = str(storage_state_path)
    return browser.new_context(**options)


def _is_authenticated(page: Page, timeout_ms: int) -> bool:
    try:
        page.goto(AUTH_CHECK_URL, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(1500)
    except Exception:
        return False

    current_url = page.url.lower()
    return "/mnjuser/homepage" in current_url and "/nlogin/" not in current_url


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage the authenticated Naukri browser session."
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open a browser, log in manually, and save the authenticated state.",
    )
    args = parser.parse_args()

    if not args.login:
        parser.error("Specify --login to create or refresh Naukri authentication.")

    state_path = create_naukri_login_state()
    print(f"Authenticated Naukri state saved to: {state_path}")


if __name__ == "__main__":
    main()
