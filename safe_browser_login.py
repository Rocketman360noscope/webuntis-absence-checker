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


def _raise_password_failure(page: Page) -> None:
    error = _visible_error_text(page)
    if _is_locked_message(error):
        raise BrowserAutomationError(
            "WebUntis reports that this user is temporarily locked. Do not retry; "
            "wait for the configured lock period or ask a WebUntis administrator to unlock the account."
        )
    suffix = f" Visible error: {error}" if error else ""
    raise BrowserAutomationError(
        "Password login did not advance. No automatic retry was made. "
        "Check WEBUNTIS_USERNAME and WEBUNTIS_PASSWORD in .env." + suffix
    )


def _wait_for_otp_or_login_completion(page: Page):
    """Wait through the SPA transition after the password submission.

    The password field can disappear several seconds before the browser-2FA field
    is mounted. Therefore disappearance of the password field alone is not proof
    that login has completed.
    """
    deadline = time.time() + 18
    password_gone_since: float | None = None

    while time.time() < deadline:
        otp_input = _semantic_otp_input(page)
        if otp_input is not None:
            return otp_input

        if _password_is_visible(page):
            password_gone_since = None
            error = _visible_error_text(page)
            if error:
                _raise_password_failure(page)
        else:
            if password_gone_since is None:
                password_gone_since = time.time()

            # Give the WebUntis single-page app enough time to mount the 2FA form.
            if time.time() - password_gone_since >= 5:
                fallback = _fallback_otp_input(page)
                if fallback is not None:
                    return fallback
                # No password and no OTP field after a stable transition means
                # that this account completed login without a browser-2FA step.
                return None

        page.wait_for_timeout(250)

    if _password_is_visible(page):
        _raise_password_failure(page)

    fallback = _fallback_otp_input(page)
    if fallback is not None:
        return fallback

    raise BrowserAutomationError(
        "WebUntis did not show either the browser 2FA form or a completed login state in time. "
        "No automatic retry was made."
    )


def _submit_one_otp(page: Page, settings: Settings, otp_input) -> None:
    otp = _fresh_otp(_otp_secret(settings))
    otp_input.fill(otp)
    _click_submit(page)

    deadline = time.time() + 15
    otp_gone_since: float | None = None

    while time.time() < deadline:
        current_otp = _semantic_otp_input(page)
        if current_otp is None:
            current_otp = _fallback_otp_input(page)

        if current_otp is not None:
            otp_gone_since = None
            error = _visible_error_text(page)
            if error:
                if _is_locked_message(error):
                    raise BrowserAutomationError(
                        "WebUntis reports that this user is temporarily locked. No further login attempt was made."
                    )
                raise BrowserAutomationError(
                    "The WebUntis browser 2FA code was rejected. No automatic retry was made. "
                    "Check WEBUNTIS_TOTP_SECRET before trying again. Visible error: " + error
                )
        elif _password_is_visible(page):
            _raise_password_failure(page)
        else:
            if otp_gone_since is None:
                otp_gone_since = time.time()
            # Wait briefly so a disappearing field during a route transition is
            # not mistaken for a completed login too early.
            if time.time() - otp_gone_since >= 2:
                page.wait_for_timeout(1000)
                return

        page.wait_for_timeout(250)

    error = _visible_error_text(page)
    if _is_locked_message(error):
        raise BrowserAutomationError(
            "WebUntis reports that this user is temporarily locked. No further login attempt was made."
        )
    suffix = f" Visible error: {error}" if error else ""
    raise BrowserAutomationError(
        "WebUntis did not confirm the browser 2FA login in time. No automatic retry was made." + suffix
    )


def login_once(page: Page, settings: Settings) -> None:
    """Log in with at most one password attempt and one browser-2FA attempt."""
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

    otp_input = _wait_for_otp_or_login_completion(page)
    if otp_input is not None:
        _submit_one_otp(page, settings, otp_input)
    else:
        page.wait_for_timeout(1200)
