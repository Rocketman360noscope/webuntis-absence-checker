from __future__ import annotations

from datetime import date
from typing import Any

import webuntis

from config import Settings
from qr_auth import otp_login


class WebUntisClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session: webuntis.Session | None = None

    def __enter__(self) -> "WebUntisClient":
        if self.settings.qr_uri:
            server, school, username, jsessionid, http = otp_login(
                self.settings.qr_uri,
                self.settings.useragent,
            )
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

        # Prime caches because AbsenceObject resolves students through them.
        self.session.students()
        self.session.klassen()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.session is not None:
            self.session.logout(suppress_errors=True)

    def _s(self) -> webuntis.Session:
        if self.session is None:
            raise RuntimeError("WebUntis session is not initialized.")
        return self.session

    def current_schoolyear_dates(self) -> tuple[date, date]:
        current = self._s().schoolyears().current
        return current.start.date(), current.end.date()

    def class_exists(self, class_name: str) -> bool:
        wanted = class_name.casefold()
        return any(k.name.casefold() == wanted for k in self._s().klassen(from_cache=True))

    def absences(self, start: date, end: date):
        return self._s().timetable_with_absences(start=start, end=end)
