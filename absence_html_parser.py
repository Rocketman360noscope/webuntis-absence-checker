from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import csv
import re

from bs4 import BeautifulSoup


@dataclass
class AbsenceRow:
    student: str
    class_name: str
    date: str
    time: str
    subject: str
    teacher: str
    absent_days: int
    absent_hours: int
    absent_minutes: int
    counts: bool
    reason: str
    status: str


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _int(text: str) -> int:
    match = re.search(r"-?\d+", _clean(text))
    return int(match.group(0)) if match else 0


def _looks_like_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", _clean(value)))


def _looks_like_time(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}", _clean(value)))


def _date_sort_key(value: str) -> tuple[int, int, int]:
    try:
        day, month, year = (int(part) for part in value.split("."))
        return year, month, day
    except (TypeError, ValueError):
        return 9999, 12, 31


def _time_bounds(value: str) -> tuple[str, str]:
    match = re.fullmatch(r"\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*", value or "")
    return match.groups() if match else ("", "")


def _unique_text(values: list[str]) -> str:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean(value)
        marker = cleaned.casefold()
        if cleaned and marker not in seen:
            seen.add(marker)
            result.append(cleaned)
    return " | ".join(result)


def parse_absence_rows(page: str) -> list[AbsenceRow]:
    """Parse rendered WebUntis absence rows using the date cell as anchor."""
    soup = BeautifulSoup(page, "html.parser")
    rows: list[AbsenceRow] = []

    for tr in soup.find_all("tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 12:
            continue

        texts = [_clean(td.get_text(" ", strip=True)) for td in cells]
        date_idx = next((i for i, value in enumerate(texts) if _looks_like_date(value)), None)
        if date_idx is None or date_idx < 3:
            continue

        # Current WebUntis layout:
        # selection | student | class | weekday | date | time | subject |
        # teacher | absent days | absent hours | absent minutes | counts |
        # absence reason | status | optional note
        student_idx = date_idx - 3
        class_idx = date_idx - 2

        student = texts[student_idx]
        class_name = texts[class_idx]
        time_value = texts[date_idx + 1] if date_idx + 1 < len(texts) else ""

        if not student or not class_name or not _looks_like_time(time_value):
            continue

        subject = texts[date_idx + 2] if date_idx + 2 < len(texts) else ""
        teacher = texts[date_idx + 3] if date_idx + 3 < len(texts) else ""
        absent_days = _int(texts[date_idx + 4]) if date_idx + 4 < len(texts) else 0
        absent_hours = _int(texts[date_idx + 5]) if date_idx + 5 < len(texts) else 0
        absent_minutes = _int(texts[date_idx + 6]) if date_idx + 6 < len(texts) else 0

        counts_idx = date_idx + 7
        counts = False
        if counts_idx < len(cells):
            checkbox = cells[counts_idx].find("input", attrs={"type": "checkbox"})
            if checkbox is not None:
                counts = checkbox.has_attr("checked")

        reason = texts[date_idx + 8] if date_idx + 8 < len(texts) else ""
        status = texts[date_idx + 9] if date_idx + 9 < len(texts) else ""

        rows.append(
            AbsenceRow(
                student=student,
                class_name=class_name,
                date=texts[date_idx],
                time=time_value,
                subject=subject,
                teacher=teacher,
                absent_days=absent_days,
                absent_hours=absent_hours,
                absent_minutes=absent_minutes,
                counts=counts,
                reason=reason,
                status=status,
            )
        )

    if not rows:
        raise RuntimeError(
            "The WebUntis page was received, but no absence rows could be recognized."
        )

    return rows


def write_detail_csv(rows: list[AbsenceRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow([
            "Schüler*in", "Klasse", "Datum", "Zeit", "Fach", "Lehrkraft",
            "Fehltage", "Fehlstunden", "Fehlminuten", "Zählt", "Abwesenheitsgrund", "Status"
        ])
        for row in rows:
            writer.writerow([
                row.student, row.class_name, row.date, row.time, row.subject,
                row.teacher, row.absent_days, row.absent_hours,
                row.absent_minutes, "ja" if row.counts else "nein",
                row.reason, row.status,
            ])


def write_daily_csv(rows: list[AbsenceRow], path: Path) -> int:
    """Write one row per student and date while retaining WebUntis totals."""
    groups: dict[tuple[str, str, str], list[AbsenceRow]] = defaultdict(list)
    for row in rows:
        groups[(row.student, row.class_name, row.date)].append(row)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow([
            "Schüler*in", "Klasse", "Datum", "Beginn", "Ende",
            "Unterrichtseinträge", "Fehltage", "Fehlstunden", "Fehlminuten",
            "Verspätung", "Abwesenheitsgründe", "Status", "Fächer"
        ])

        ordered_keys = sorted(
            groups,
            key=lambda key: (key[0].casefold(), _date_sort_key(key[2]), key[1].casefold()),
        )
        for student, class_name, date_value in ordered_keys:
            group = groups[(student, class_name, date_value)]
            starts: list[str] = []
            ends: list[str] = []
            for row in group:
                start, end = _time_bounds(row.time)
                if start:
                    starts.append(start)
                if end:
                    ends.append(end)

            writer.writerow([
                student,
                class_name,
                date_value,
                min(starts) if starts else "",
                max(ends) if ends else "",
                len(group),
                sum(row.absent_days for row in group),
                sum(row.absent_hours for row in group),
                sum(row.absent_minutes for row in group),
                "ja" if any("verspät" in row.reason.casefold() for row in group) else "nein",
                _unique_text([row.reason for row in group]),
                _unique_text([row.status for row in group]),
                _unique_text([row.subject for row in group]),
            ])

    return len(groups)


def write_summary_csv(rows: list[AbsenceRow], path: Path) -> None:
    summary: dict[str, dict[str, object]] = defaultdict(lambda: {
        "entries": 0,
        "dates": set(),
        "days": 0,
        "hours": 0,
        "minutes": 0,
        "late_dates": set(),
        "excused_entries": 0,
        "unexcused_entries": 0,
        "open_entries": 0,
    })

    for row in rows:
        item = summary[row.student]
        item["entries"] = int(item["entries"]) + 1
        cast_dates = item["dates"]
        assert isinstance(cast_dates, set)
        cast_dates.add(row.date)
        item["days"] = int(item["days"]) + row.absent_days
        item["hours"] = int(item["hours"]) + row.absent_hours
        item["minutes"] = int(item["minutes"]) + row.absent_minutes

        if "verspät" in row.reason.casefold():
            late_dates = item["late_dates"]
            assert isinstance(late_dates, set)
            late_dates.add(row.date)

        status = row.status.casefold()
        if "unentsch" in status or "nicht entsch" in status:
            item["unexcused_entries"] = int(item["unexcused_entries"]) + 1
        elif "entsch" in status:
            item["excused_entries"] = int(item["excused_entries"]) + 1
        elif "offen" in status or not status:
            item["open_entries"] = int(item["open_entries"]) + 1

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow([
            "Schüler*in", "Unterrichtseinträge", "Tage mit Einträgen",
            "Fehltage", "Fehlstunden", "Fehlminuten", "Verspätungstage",
            "Entschuldigte Unterrichtseinträge", "Unentschuldigte Unterrichtseinträge",
            "Offene/unklare Unterrichtseinträge"
        ])
        for student in sorted(summary, key=str.casefold):
            item = summary[student]
            dates = item["dates"]
            late_dates = item["late_dates"]
            assert isinstance(dates, set)
            assert isinstance(late_dates, set)
            writer.writerow([
                student,
                item["entries"],
                len(dates),
                item["days"],
                item["hours"],
                item["minutes"],
                len(late_dates),
                item["excused_entries"],
                item["unexcused_entries"],
                item["open_entries"],
            ])
