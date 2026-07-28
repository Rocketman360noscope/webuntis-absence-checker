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


def write_summary_csv(rows: list[AbsenceRow], path: Path) -> None:
    summary: dict[str, dict[str, int]] = defaultdict(lambda: {
        "entries": 0,
        "days": 0,
        "hours": 0,
        "minutes": 0,
        "late_entries": 0,
        "excused_entries": 0,
        "unexcused_entries": 0,
        "open_entries": 0,
    })

    for row in rows:
        item = summary[row.student]
        item["entries"] += 1
        item["days"] += row.absent_days
        item["hours"] += row.absent_hours
        item["minutes"] += row.absent_minutes

        if "verspät" in row.reason.casefold():
            item["late_entries"] += 1

        status = row.status.casefold()
        if "unentsch" in status or "nicht entsch" in status:
            item["unexcused_entries"] += 1
        elif "entsch" in status:
            item["excused_entries"] += 1
        elif "offen" in status or not status:
            item["open_entries"] += 1

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow([
            "Schüler*in", "Einträge", "Fehltage", "Fehlstunden", "Fehlminuten",
            "Verspätungs-Einträge", "Entschuldigte Einträge", "Unentschuldigte Einträge", "Offene/unklare Einträge"
        ])
        for student in sorted(summary, key=str.casefold):
            item = summary[student]
            writer.writerow([
                student, item["entries"], item["days"], item["hours"], item["minutes"],
                item["late_entries"], item["excused_entries"], item["unexcused_entries"], item["open_entries"],
            ])
