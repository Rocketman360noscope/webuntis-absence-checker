from __future__ import annotations

from datetime import date
import json
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from browser_automation import BrowserAutomationError, _safe_form_description
from config import Settings
from safe_browser_login import login_once


def _yyyymmdd(value: date) -> int:
    return value.year * 10000 + value.month * 100 + value.day


def _open_authenticated_absence_page(page, settings: Settings) -> str:
    """Open the absence filter and wait for its server-rendered class selector.

    A second GET is allowed when WebUntis briefly serves an empty transition page.
    This never repeats the password or 2FA login attempt.
    """
    embedded = f"https://{settings.server}/WebUntis/embedded.do?showSidebar=true"
    page.goto(embedded, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1200)

    last_status: int | None = None
    last_url = page.url

    for attempt in range(2):
        cache_buster = str(int(time.time() * 1000))
        url = f"https://{settings.server}/WebUntis/absencetimes.do?request.preventCache={cache_buster}"
        response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        last_status = response.status if response is not None else None
        last_url = page.url

        if last_status == 403:
            raise BrowserAutomationError(
                "WebUntis returned 403 when opening the absence page after browser login. "
                "No additional login attempt was made."
            )

        try:
            page.wait_for_selector("#klasseOrStudentgroupId", state="attached", timeout=12_000)
            return url
        except PlaywrightTimeoutError:
            if attempt == 0:
                # Harmless navigation retry only; credentials and OTP are not submitted again.
                page.goto(embedded, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2000)
                continue

    try:
        title = page.title()
    except Exception:
        title = ""
    try:
        html_chars = len(page.content())
    except Exception:
        html_chars = 0

    raise BrowserAutomationError(
        "Logged-in absence filter was not found after waiting and one safe page reload. "
        f"HTTP status: {last_status or '-'}, current URL: {last_url}, "
        f"page title: {title or '-'}, HTML characters: {html_chars}. "
        "No additional password or 2FA attempt was made. Visible form: "
        + _safe_form_description(page)
    )


def _submit_absence_filter_direct(
    page,
    settings: Settings,
    start: date,
    end: date,
) -> str:
    """Submit the absence filter with a direct authenticated browser POST.

    WebUntis' date-range Dojo widget keeps its own internal state and can reset
    the selected range to CURRENT_DATE when its submit() method is called. This
    function bypasses that widget and sends the intended form values directly
    from the already-authenticated browser context.
    """
    url = _open_authenticated_absence_page(page, settings)

    csrf = page.locator('input[name="_csrf"]').get_attribute("value")
    if not csrf:
        raise BrowserAutomationError("The logged-in absence page did not contain a CSRF token.")

    cache_buster = str(int(time.time() * 1000))
    post_url = f"https://{settings.server}/WebUntis/absencetimes.do?request.preventCache={cache_buster}"
    date_range = {
        "name": "",
        "id": -1,
        "type": "CURRENT_SCHOOLYEAR",
        "endDate": _yyyymmdd(end),
        "startDate": _yyyymmdd(start),
        "restrictToSchoolyear": True,
    }

    result = page.evaluate(
        """
        async ([url, cacheBuster, classId, dateRange, csrf]) => {
          const form = new URLSearchParams();
          form.append('request.preventCache', cacheBuster);
          form.append('klasseOrStudentgroupId', classId);
          form.append('studentId', '-1');
          form.append('subjectId', '-1');
          form.append('absenceReasonId', '-1');
          form.append('periodExcuseStatusId', '-1');
          form.append('selectedDateRange', dateRange);
          form.append('withAbsences', 'true');
          form.append('_withAbsences', 'on');
          form.append('withLateness', 'true');
          form.append('_withLateness', 'on');
          form.append('_onlyExams', 'on');
          form.append('_onlyOpen', 'on');
          form.append('_csrf', csrf);

          const response = await fetch(url, {
            method: 'POST',
            credentials: 'include',
            headers: {
              'Accept': 'text/html, */*; q=0.01',
              'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
              'X-Requested-With': 'XMLHttpRequest'
            },
            body: form.toString()
          });

          return {
            status: response.status,
            url: response.url,
            text: await response.text()
          };
        }
        """,
        [
            post_url,
            cache_buster,
            settings.class_id,
            json.dumps(date_range, separators=(",", ":")),
            csrf,
        ],
    )

    status = int(result["status"])
    body = str(result["text"])

    if status != 200:
        raise BrowserAutomationError(f"Direct absence POST returned HTTP {status}.")
    if settings.class_name not in body:
        raise BrowserAutomationError(
            "Direct absence POST returned HTML, but the configured class was not found."
        )

    return body


def fetch_absence_html_browser_v2(
    settings: Settings,
    start: date,
    end: date,
    *,
    headless: bool = False,
) -> str:
    """Login in Chromium and fetch the absence HTML with a direct form POST."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(locale="de-DE")
        page = context.new_page()
        try:
            login_once(page, settings)
            return _submit_absence_filter_direct(page, settings, start, end)
        finally:
            browser.close()
