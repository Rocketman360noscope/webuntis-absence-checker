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


def parse_absence_rows(page: str) -> list[AbsenceRow]:
    soup = BeautifulSoup(page, "html.parser")

    target = None
    for table in soup.find_all("table"):
        header = _clean(table.get_text(" ", strip=True)).casefold()
        if "fehlstd" in header and "fehlmin" in header and "schüler" in header:
            target = table
            break

    if target is None:
        raise RuntimeError("Could not find the WebUntis absence table in the HTML response.")

    rows: list[AbsenceRow] = []
    for tr in target.find_all("tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 10:
            continue

        texts = [_clean(td.get_text(" ", strip=True)) for td in cells]

        # WebUntis currently renders an initial selection-checkbox column.
        # The expected data order after that is:
        # student, class, date, time, subject, teacher, absent days, hours,
        # minutes, counts, reason, status.
        offset = 1 if cells[0].find("input") is not None else 0
        values = texts[offset:]
        if len(values) < 9:
            continue

        student = values[0]
        if not student or student.casefold() in {"schüler*innen", "schüler"}:
            continue

        class_name = values[1] if len(values) > 1 else ""
        date = values[2] if len(values) > 2 else ""
        time_value = values[3] if len(values) > 3 else ""
        subject = values[4] if len(values) > 4 else ""
        teacher = values[5] if len(values) > 5 else ""
        absent_days = _int(values[6]) if len(values) > 6 else 0
        absent_hours = _int(values[7]) if len(values) > 7 else 0
        absent_minutes = _int(values[8]) if len(values) > 8 else 0

        counts = False
        reason = ""
        status = ""

        # Prefer locating the "counts" checkbox structurally, then use the
        # remaining textual tail for reason/status. This is more robust across
        # slightly different WebUntis layouts.
        counts_index = None
        for idx, cell in enumerate(cells[offset + 9 :], start=9):
            checkbox = cell.find("input", attrs={"type": "checkbox"})
            if checkbox is not None:
                counts_index = idx
                counts = checkbox.has_attr("checked")
                break

        if counts_index is not None:
            tail_start = counts_index + 1
            tail = texts[offset + tail_start :]
        else:
            tail = values[9:]

        if tail:
            reason = tail[0]
        if len(tail) > 1:
            status = tail[-1]

        rows.append(
            AbsenceRow(
                student=student,
                class_name=class_name,
                date=date,
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
        status = row.status.casefold()
        if "unentsch" in status:
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
            "Entschuldigte Einträge", "Unentschuldigte Einträge", "Offene/unklare Einträge"
        ])
        for student in sorted(summary, key=str.casefold):
            item = summary[student]
            writer.writerow([
                student, item["entries"], item["days"], item["hours"], item["minutes"],
                item["excused_entries"], item["unexcused_entries"], item["open_entries"],
            ])
