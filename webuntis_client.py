from __future__ import annotations

from datetime import date
from typing import Any

import webuntis

from config import Settings


class WebUntisClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = webuntis.Session(
            username=settings.username,
            password=settings.password,
            server=settings.server,
            school=settings.school,
            useragent=settings.useragent,
            login_repeat=1,
        )

    def __enter__(self) -> "WebUntisClient":
        self.session.login()
        # Prime caches because AbsenceObject resolves students through them.
        self.session.students()
        self.session.klassen()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.session.logout(suppress_errors=True)

    def current_schoolyear_dates(self) -> tuple[date, date]:
        current = self.session.schoolyears().current
        return current.start.date(), current.end.date()

    def class_exists(self, class_name: str) -> bool:
        wanted = class_name.casefold()
        return any(k.name.casefold() == wanted for k in self.session.klassen(from_cache=True))

    def absences(self, start: date, end: date):
        return self.session.timetable_with_absences(start=start, end=end)
