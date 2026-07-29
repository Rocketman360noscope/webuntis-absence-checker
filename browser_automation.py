from __future__ import annotations

from datetime import date
import json
import re
import time

import pyotp
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from config import Settings


class BrowserAutomationError(RuntimeError):
    pass


def _yyyymmdd(value: date) -> int:
    return value.year * 10000 + value.month * 100 + value.day


def _first_visible(page: Page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector)
        for i in range(locator.count()):
            candidate = locator.nth(i)
            try:
                if candidate.is_visible():
                    return candidate
            except Exception:
                continue
    return None


def _click_submit(page: Page) -> None:
    button = _first_visible(
        page,
        [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Anmelden")',
            'button:has-text("Login")',
            'button:has-text("Weiter")',
            'button:has-text("Bestätigen")',
            'button:has-text("Bestätigen & anmelden")',
        ],
    )
    if button is None:
        raise BrowserAutomationError("Could not find a visible login/continue button.")
    button.click()


def _safe_form_description(page: Page) -> str:
    items: list[str] = []
    for i in range(page.locator("input").count()):
        el = page.locator("input").nth(i)
        try:
            if not el.is_visible():
                continue
            items.append(
                "input(" + ", ".join(
                    part for part in [
                        f"type={el.get_attribute('type') or 'text'}",
                        f"name={el.get_attribute('name') or '-'}",
                        f"autocomplete={el.get_attribute('autocomplete') or '-'}",
                        f"placeholder={el.get_attribute('placeholder') or '-'}",
                    ] if part
                ) + ")"
            )
        except Exception:
            continue
    return "; ".join(items) or "no visible inputs"


def _visible_error_text(page: Page) -> str:
    selectors = [
        '[role="alert"]',
        '.error',
        '.alert',
        '[class*="error" i]',
        '[class*="alert" i]',
        '.MuiFormHelperText-root',
    ]
    messages: list[str] = []
    for selector in selectors:
        locator = page.locator(selector)
        for i in range(min(locator.count(), 20)):
            item = locator.nth(i)
            try:
                if not item.is_visible():
                    continue
                text = re.sub(r"\s+", " ", item.inner_text()).strip()
                if text and text not in messages:
                    messages.append(text)
            except Exception:
                continue
    return " | ".join(messages[:5])


def _password_is_visible(page: Page) -> bool:
    field = _first_visible(page, ['input[autocomplete="current-password"]', 'input[type="password"]'])
    return field is not None


def _semantic_otp_input(page: Page):
    return _first_visible(
        page,
        [
            'input[autocomplete="one-time-code"]',
            'input[name*="otp" i]',
            'input[name*="totp" i]',
            'input[name*="token" i]',
            'input[name*="code" i]',
            'input[type="tel"]',
            'input[type="number"]',
        ],
    )


def _fallback_otp_input(page: Page):
    visible_text_inputs = []
    locator = page.locator('input[type="text"], input:not([type])')
    for i in range(locator.count()):
        el = locator.nth(i)
        try:
            if el.is_visible():
                visible_text_inputs.append(el)
        except Exception:
            pass
    return visible_text_inputs[0] if len(visible_text_inputs) == 1 else None


def _otp_secret(settings: Settings) -> str:
    """Return the dedicated secret for the normal WebUntis browser 2FA.

    WebUntis uses a different key for Untis Mobile access. Therefore the mobile
    QR URI and WEBUNTIS_APP_SECRET must never be used for the browser login code.
    """
    secret = settings.totp_secret.replace(" ", "")
    if secret:
        return secret
    raise BrowserAutomationError(
        "A browser 2FA field appeared, but WEBUNTIS_TOTP_SECRET is empty. "
        "Enter the separate key from WebUntis Two-Factor Authentication, not the Untis Mobile access key."
    )


def _fresh_otp(secret: str) -> str:
    totp = pyotp.TOTP(secret)
    remaining = totp.interval - (time.time() % totp.interval)
    if remaining < 8:
        time.sleep(remaining + 0.7)
    return totp.now()


def _login(page: Page, settings: Settings) -> None:
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
        suffix = f" Visible error: {error}" if error else ""
        raise BrowserAutomationError(
            "Password login did not advance; the username/password form is still visible. "
            "Check WEBUNTIS_USERNAME and WEBUNTIS_PASSWORD in .env." + suffix
        )

    if otp_input is None:
        otp_input = _fallback_otp_input(page)

    if otp_input is not None:
        secret = _otp_secret(settings)

        for attempt in range(2):
            otp = _fresh_otp(secret)
            otp_input.fill(otp)
            _click_submit(page)

            deadline = time.time() + 8
            while time.time() < deadline:
                page.wait_for_timeout(250)
                current_otp = _semantic_otp_input(page)
                if current_otp is None and not _password_is_visible(page):
                    page.wait_for_timeout(1200)
                    return

            if attempt == 0:
                totp = pyotp.TOTP(secret)
                remaining = totp.interval - (time.time() % totp.interval)
                time.sleep(remaining + 0.7)
                otp_input = _semantic_otp_input(page) or _fallback_otp_input(page)
                if otp_input is None:
                    break

        error = _visible_error_text(page)
        suffix = f" Visible error: {error}" if error else ""
        raise BrowserAutomationError(
            "The WebUntis browser 2FA code was rejected twice. Check that WEBUNTIS_TOTP_SECRET is the "
            "separate Two-Factor Authentication key currently used by FreeOTP." + suffix
        )

    page.wait_for_timeout(1200)


def _submit_absence_filter(
    page: Page,
    settings: Settings,
    start: date,
    end: date,
) -> str:
    embedded = f"https://{settings.server}/WebUntis/embedded.do?showSidebar=true"
    page.goto(embedded, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1000)

    url = f"https://{settings.server}/WebUntis/absencetimes.do?request.preventCache={int(time.time() * 1000)}"
    response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1000)

    if response is not None and response.status == 403:
        raise BrowserAutomationError(
            "WebUntis returned 403 when opening the absence page after browser login. "
            "Login may not have completed. Visible form: " + _safe_form_description(page)
        )

    class_select = page.locator("#klasseOrStudentgroupId")
    if class_select.count() == 0:
        raise BrowserAutomationError(
            "Logged-in absence filter was not found. Current URL: " + page.url + ". Visible form: " + _safe_form_description(page)
        )

    date_range = {
        "name": "",
        "id": -1,
        "type": "CURRENT_SCHOOLYEAR",
        "endDate": _yyyymmdd(end),
        "startDate": _yyyymmdd(start),
        "restrictToSchoolyear": True,
    }

    page.evaluate(
        """
        ([classId, dateRange]) => {
          const setValue = (name, value) => {
            const el = document.querySelector(`[name="${name}"]`);
            if (el) el.value = value;
          };
          const klass = document.querySelector('#klasseOrStudentgroupId');
          if (klass) klass.value = classId;
          setValue('studentId', '-1');
          setValue('subjectId', '-1');
          setValue('absenceReasonId', '-1');
          setValue('periodExcuseStatusId', '-1');
          setValue('selectedDateRange', dateRange);
          const abs = document.querySelector('[name="withAbsences"]');
          if (abs) abs.checked = true;
          const late = document.querySelector('[name="withLateness"]');
          if (late) late.checked = true;
          const open = document.querySelector('[name="onlyOpen"]');
          if (open) open.checked = false;
          const exams = document.querySelector('[name="onlyExams"]');
          if (exams) exams.checked = false;
        }
        """,
        [settings.class_id, json.dumps(date_range, separators=(",", ":"))],
    )

    try:
        with page.expect_response(
            lambda r: "absencetimes.do" in r.url and r.request.method == "POST",
            timeout=30_000,
        ) as response_info:
            page.evaluate(
                """
                () => {
                  if (window.absenceTimesForm && typeof window.absenceTimesForm.submit === 'function') {
                    window.absenceTimesForm.submit();
                    return;
                  }
                  const form = document.querySelector('form');
                  if (!form) throw new Error('absence form not found');
                  form.requestSubmit();
                }
                """
            )
        result = response_info.value
        body = result.text()
    except PlaywrightTimeoutError as exc:
        raise BrowserAutomationError(
            "Timed out waiting for the WebUntis absence POST after setting the filters."
        ) from exc

    if result.status != 200:
        raise BrowserAutomationError(f"Absence POST returned HTTP {result.status}.")
    if settings.class_name not in body:
        raise BrowserAutomationError("Absence POST returned HTML, but the configured class was not found.")

    return body


def fetch_absence_html_browser(
    settings: Settings,
    start: date,
    end: date,
    *,
    headless: bool = False,
) -> str:
    """Login in a real browser and fetch the rendered WebUntis absence HTML."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(locale="de-DE")
        page = context.new_page()
        try:
            _login(page, settings)
            return _submit_absence_filter(page, settings, start, end)
        finally:
            browser.close()
