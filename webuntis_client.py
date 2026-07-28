from __future__ import annotations

from datetime import date
import html
import json
import re
import time
from typing import Any

import requests
import webuntis

from config import Settings
from qr_auth import otp_login, otp_login_with_secret


class WebUntisClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session: webuntis.Session | None = None
        self.http: requests.Session | None = None
        self.server = settings.server

    def __enter__(self) -> "WebUntisClient":
        if self.settings.qr_uri:
            server, school, username, jsessionid, http = otp_login(
                self.settings.qr_uri,
                self.settings.useragent,
            )
            self.server = server
            self.http = http
        elif self.settings.app_secret:
            server = self.settings.server
            school = self.settings.school
            username = self.settings.username
            jsessionid, http = otp_login_with_secret(
                server,
                school,
                username,
                self.settings.app_secret,
                self.settings.useragent,
            )
            self.server = server
            self.http = http
        else:
            self.session = webuntis.Session(
                username=self.settings.username,
                password=self.settings.password,
                server=self.settings.server,
                school=self.settings.school,
                useragent=self.settings.useragent,
                login_repeat=1,
            )
            self.session.login()
            server = school = username = jsessionid = http = None

        if self.session is None:
            self.session = webuntis.Session(
                username=username,
                password="",
                server=server,
                school=school,
                useragent=self.settings.useragent,
                jsessionid=jsessionid,
                _http_session=http,
                login_repeat=0,
            )

        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.session is not None:
            self.session.logout(suppress_errors=True)

    def _s(self) -> webuntis.Session:
        if self.session is None:
            raise RuntimeError("WebUntis session is not initialized.")
        return self.session

    def _http(self) -> requests.Session:
        if self.http is not None:
            return self.http
        raise RuntimeError("Browser-style absence fetch currently requires app/QR authentication.")

    def current_schoolyear_dates(self) -> tuple[date, date]:
        current = self._s().schoolyears().current
        return current.start.date(), current.end.date()

    @staticmethod
    def _yyyymmdd(value: date) -> int:
        return value.year * 10000 + value.month * 100 + value.day

    @staticmethod
    def _extract_csrf(page: str) -> str:
        patterns = [
            r'name=["\']_csrf["\'][^>]*value=["\']([^"\']+)',
            r'value=["\']([^"\']+)["\'][^>]*name=["\']_csrf["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, page, flags=re.IGNORECASE)
            if match:
                return html.unescape(match.group(1))
        raise RuntimeError("Could not find WebUntis CSRF token on absencetimes.do page.")

    def browser_absence_times_html(
        self,
        start: date,
        end: date,
        class_id: str,
    ) -> str:
        """Replay the teacher browser's absencetimes.do request.

        This intentionally avoids getStudents(), which the teacher account is not
        permitted to call, and instead requests the same rendered class-register
        absence view that the WebUntis browser UI uses.
        """
        http_session = self._http()
        base = f"https://{self.server}/WebUntis/absencetimes.do"
        cache_buster = str(int(time.time() * 1000))

        # First load the page so the authenticated session receives a fresh CSRF token.
        page = http_session.get(
            base,
            params={"request.preventCache": cache_buster},
            headers={"Accept": "text/html,application/xhtml+xml"},
            timeout=30,
        )
        page.raise_for_status()
        csrf = self._extract_csrf(page.text)

        date_range = {
            "name": "",
            "id": -1,
            "type": "CURRENT_SCHOOLYEAR",
            "endDate": self._yyyymmdd(end),
            "startDate": self._yyyymmdd(start),
            "restrictToSchoolyear": True,
        }

        form = {
            "request.preventCache": str(int(time.time() * 1000)),
            "klasseOrStudentgroupId": class_id,
            "studentId": "-1",
            "subjectId": "-1",
            "absenceReasonId": "-1",
            "periodExcuseStatusId": "-1",
            "selectedDateRange": json.dumps(date_range, separators=(",", ":")),
            "withAbsences": "true",
            "_withAbsences": "on",
            "withLateness": "true",
            "_withLateness": "on",
            "_onlyExams": "on",
            "_onlyOpen": "on",
            "_csrf": csrf,
        }

        response = http_session.post(
            base,
            params={"request.preventCache": form["request.preventCache"]},
            data=form,
            headers={
                "Accept": "text/html, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": page.url,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.text

    def absences(self, start: date, end: date):
        return self._s().timetable_with_absences(start=start, end=end)
