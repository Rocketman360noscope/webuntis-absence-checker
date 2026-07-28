from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import csv


EXCUSED_WORDS = {"excused", "entschuldigt", "e", "true", "1"}
UNEXCUSED_WORDS = {"unexcused", "unentschuldigt", "u", "false", "0"}


@dataclass
class StudentSummary:
    name: str
    excused_minutes: int = 0
    unexcused_minutes: int = 0
    unknown_minutes: int = 0
    entries: int = 0

    @property
    def total_minutes(self) -> int:
        return self.excused_minutes + self.unexcused_minutes + self.unknown_minutes


def _status_bucket(status: object) -> str:
    value = str(status or "").strip().casefold()
    if value in EXCUSED_WORDS or "excused" in value or "entschuld" in value and "un" not in value:
        return "excused"
    if value in UNEXCUSED_WORDS or "unexcused" in value or "unentschuld" in value:
        return "unexcused"
    return "unknown"


def _matches_class(absence: object, class_name: str) -> bool:
    """Best-effort class filter without triggering any additional API calls."""
    wanted = class_name.casefold()
    raw = getattr(absence, "_data", {}) or {}

    candidates: list[str] = []
    # Read raw fields only. Accessing some convenience properties in
    # python-webuntis may cause follow-up API requests.
    for key in ("className", "klasseName", "class", "klasse", "studentGroup"):
        value = raw.get(key)
        if isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, dict):
            candidates.extend(str(v) for v in value.values() if isinstance(v, str))

    if not candidates:
        return True

    return any(wanted in candidate.casefold() for candidate in candidates)


def _raw_student_name(raw: dict) -> str:
    """Resolve a display name exclusively from the absence payload.

    Never use AbsenceObject.name/student here: those properties call
    getStudents(), which many teacher accounts are not allowed to use.
    """
    for key in ("studentName", "student", "name", "studentLongName", "longName"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            first = value.get("foreName") or value.get("firstName") or ""
            last = value.get("longName") or value.get("lastName") or value.get("name") or ""
            combined = f"{first} {last}".strip()
            if combined:
                return combined

    # Keep entries separated even if this WebUntis server only supplies a
    # student key/id in the absence payload.
    student_id = raw.get("studentId") or raw.get("studentid") or raw.get("studentKey")
    if student_id not in (None, ""):
        return f"Schüler-ID {student_id}"

    return "Unbekannter Schüler"


def aggregate_absences(absences: object, class_name: str) -> tuple[list[StudentSummary], bool]:
    summaries: dict[str, StudentSummary] = defaultdict(lambda: StudentSummary(name=""))
    saw_class_metadata = False

    for absence in absences:
        raw = getattr(absence, "_data", {}) or {}
        if any(k in raw for k in ("className", "klasseName", "class", "klasse", "studentGroup")):
            saw_class_metadata = True

        if not _matches_class(absence, class_name):
            continue

        name = _raw_student_name(raw)
        summary = summaries[name]
        summary.name = name

        # Read the payload directly so no lazy WebUntis properties can trigger
        # forbidden follow-up requests.
        try:
            minutes = max(int(raw.get("absentTime", 0) or 0), 0)
        except (TypeError, ValueError):
            minutes = 0
        bucket = _status_bucket(raw.get("excuseStatus", ""))

        if bucket == "excused":
            summary.excused_minutes += minutes
        elif bucket == "unexcused":
            summary.unexcused_minutes += minutes
        else:
            summary.unknown_minutes += minutes
        summary.entries += 1

    return sorted(summaries.values(), key=lambda s: s.name.casefold()), saw_class_metadata


def write_csv(rows: list[StudentSummary], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow([
            "Name",
            "Entschuldigt (Min.)",
            "Unentschuldigt (Min.)",
            "Unklar (Min.)",
            "Gesamt (Min.)",
            "Einträge",
        ])
        for row in rows:
            writer.writerow([
                row.name,
                row.excused_minutes,
                row.unexcused_minutes,
                row.unknown_minutes,
                row.total_minutes,
                row.entries,
            ])
