from __future__ import annotations

import time

from playwright.sync_api import Page

from browser_automation import (
    BrowserAutomationError,
    _click_submit,
    _fallback_otp_input,
    _first_visible,
    _fresh_otp,
    _otp_secret,
    _password_is_visible,
    _safe_form_description,
    _semantic_otp_input,
    _visible_error_text,
)
from config import Settings


def _is_locked_message(text: str) -> bool:
    folded = text.casefold()
    return "vorübergehend gesperrt" in folded or "temporarily blocked" in folded


def login_once(page: Page, settings: Settings) -> None:
    """Log in with at most one password attempt and one browser-2FA attempt.

    This intentionally avoids automatic retries so a stale password or TOTP
    secret cannot rapidly trigger another WebUntis account lock.
    """
    if not settings.password:
        raise BrowserAutomationError(
            "WEBUNTIS_PASSWORD is empty. Browser automation needs the normal WebUntis password in .env."
        )

    login_url = f"https://{settings.server}/WebUntis/?school={settings.school}#/basic/login"
    page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1500)

    username = _first_visible(
        page,
        [
            'input[autocomplete="username"]',
            'input[name="username"]',
            'input[name="user"]',
            'input[type="text"]',
        ],
    )
    password = _first_visible(page, ['input[autocomplete="current-password"]', 'input[type="password"]'])

    if username is None or password is None:
        raise BrowserAutomationError(
            "Could not identify username/password fields. Visible form: " + _safe_form_description(page)
        )

    username.fill(settings.username)
    password.fill(settings.password)
    _click_submit(page)

    otp_input = None
    deadline = time.time() + 12
    while time.time() < deadline:
        page.wait_for_timeout(250)
        otp_input = _semantic_otp_input(page)
        if otp_input is not None:
            break
        if not _password_is_visible(page):
            break

    if _password_is_visible(page):
        error = _visible_error_text(page)
        if _is_locked_message(error):
            raise BrowserAutomationError(
                "WebUntis reports that this user is temporarily locked. Do not retry; wait for the configured lock period or ask a WebUntis administrator to unlock the account."
            )
        suffix = f" Visible error: {error}" if error else ""
        raise BrowserAutomationError(
            "Password login did not advance. No automatic retry was made. Check WEBUNTIS_USERNAME and WEBUNTIS_PASSWORD in .env."
            + suffix
        )

    if otp_input is None:
        otp_input = _fallback_otp_input(page)

    if otp_input is not None:
        otp = _fresh_otp(_otp_secret(settings))
        otp_input.fill(otp)
        _click_submit(page)

        deadline = time.time() + 8
        while time.time() < deadline:
            page.wait_for_timeout(250)
            current_otp = _semantic_otp_input(page)
            if current_otp is None and not _password_is_visible(page):
                page.wait_for_timeout(1200)
                return

        error = _visible_error_text(page)
        if _is_locked_message(error):
            raise BrowserAutomationError(
                "WebUntis reports that this user is temporarily locked. No further login attempt was made."
            )
        suffix = f" Visible error: {error}" if error else ""
        raise BrowserAutomationError(
            "The WebUntis browser 2FA code was rejected. No automatic retry was made. Check WEBUNTIS_TOTP_SECRET before trying again."
            + suffix
        )

    page.wait_for_timeout(1200)
