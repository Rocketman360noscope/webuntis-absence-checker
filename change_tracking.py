from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import csv
import json
from typing import Any

from absence_html_parser import AbsenceRow


SNAPSHOT_VERSION = 1


def _identity(row: dict[str, Any]) -> tuple[str, ...]:
    """Return a stable identity for one timetable absence entry.

    Status, reason and totals are intentionally excluded because these fields can
    change later when an excuse is processed or an entry is corrected.
    """
    return (
        str(row.get("student", "")),
        str(row.get("class_name", "")),
        str(row.get("date", "")),
        str(row.get("time", "")),
        str(row.get("subject", "")),
        str(row.get("teacher", "")),
    )


def _mutable_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(row.get("absent_days", 0)),
        int(row.get("absent_hours", 0)),
        int(row.get("absent_minutes", 0)),
        bool(row.get("counts", False)),
        str(row.get("reason", "")),
        str(row.get("status", "")),
    )


def _serialize_rows(rows: list[AbsenceRow]) -> list[dict[str, Any]]:
    return [asdict(row) for row in rows]


def load_snapshot(path: Path) -> list[dict[str, Any]] | None:
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != SNAPSHOT_VERSION:
        raise RuntimeError(
            f"Unsupported snapshot version in {path}. "
            "Delete only this generated snapshot file and run again."
        )

    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise RuntimeError(f"Invalid snapshot structure in {path}.")
    return rows


def save_snapshot(rows: list[AbsenceRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SNAPSHOT_VERSION,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "rows": _serialize_rows(rows),
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def compare_rows(
    previous: list[dict[str, Any]],
    current_rows: list[AbsenceRow],
) -> list[dict[str, Any]]:
    """Compare two snapshots without exposing data outside local report files."""
    current = _serialize_rows(current_rows)

    previous_by_id: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    current_by_id: dict[tuple[str, ...], list[dict[str, Any]]] = {}

    for row in previous:
        previous_by_id.setdefault(_identity(row), []).append(row)
    for row in current:
        current_by_id.setdefault(_identity(row), []).append(row)

    changes: list[dict[str, Any]] = []
    all_ids = sorted(set(previous_by_id) | set(current_by_id))

    for identity in all_ids:
        old_rows = previous_by_id.get(identity, [])
        new_rows = current_by_id.get(identity, [])

        old_counter = Counter(_mutable_signature(row) for row in old_rows)
        new_counter = Counter(_mutable_signature(row) for row in new_rows)

        unchanged = old_counter & new_counter
        old_remaining = list((old_counter - unchanged).elements())
        new_remaining = list((new_counter - unchanged).elements())

        paired = min(len(old_remaining), len(new_remaining))
        for index in range(paired):
            old = old_remaining[index]
            new = new_remaining[index]
            changes.append(_change_record("geändert", identity, old, new))

        for old in old_remaining[paired:]:
            changes.append(_change_record("entfernt", identity, old, None))

        for new in new_remaining[paired:]:
            changes.append(_change_record("neu", identity, None, new))

    return changes


def _change_record(
    change_type: str,
    identity: tuple[str, ...],
    old: tuple[Any, ...] | None,
    new: tuple[Any, ...] | None,
) -> dict[str, Any]:
    student, class_name, date_value, time_value, subject, teacher = identity

    old_values = old or ("", "", "", "", "", "")
    new_values = new or ("", "", "", "", "", "")

    return {
        "Änderung": change_type,
        "Schüler*in": student,
        "Klasse": class_name,
        "Datum": date_value,
        "Zeit": time_value,
        "Fach": subject,
        "Lehrkraft": teacher,
        "Fehltage vorher": old_values[0],
        "Fehltage aktuell": new_values[0],
        "Fehlstunden vorher": old_values[1],
        "Fehlstunden aktuell": new_values[1],
        "Fehlminuten vorher": old_values[2],
        "Fehlminuten aktuell": new_values[2],
        "Zählt vorher": _bool_text(old_values[3]),
        "Zählt aktuell": _bool_text(new_values[3]),
        "Grund vorher": old_values[4],
        "Grund aktuell": new_values[4],
        "Status vorher": old_values[5],
        "Status aktuell": new_values[5],
    }


def _bool_text(value: Any) -> str:
    if value == "":
        return ""
    return "ja" if bool(value) else "nein"


def write_changes_csv(changes: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "Änderung", "Schüler*in", "Klasse", "Datum", "Zeit", "Fach", "Lehrkraft",
        "Fehltage vorher", "Fehltage aktuell",
        "Fehlstunden vorher", "Fehlstunden aktuell",
        "Fehlminuten vorher", "Fehlminuten aktuell",
        "Zählt vorher", "Zählt aktuell",
        "Grund vorher", "Grund aktuell",
        "Status vorher", "Status aktuell",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, delimiter=";")
        writer.writeheader()
        writer.writerows(changes)


def safe_change_summary(changes: list[dict[str, Any]]) -> Counter[str]:
    """Return counts only, suitable for console output without student names."""
    return Counter(str(change["Änderung"]) for change in changes)
