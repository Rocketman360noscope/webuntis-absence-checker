from __future__ import annotations

from datetime import date
from pathlib import Path
from pprint import pprint
import sys

import webuntis

from absence_report import aggregate_absences, write_csv
from config import load_settings
from webuntis_client import WebUntisClient


def main() -> int:
    try:
        settings = load_settings()
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        with WebUntisClient(settings) as client:
            schoolyear_start, schoolyear_end = client.current_schoolyear_dates()
            start = settings.start_date or schoolyear_start
            end = settings.end_date or min(date.today(), schoolyear_end)

            if start > end:
                raise ValueError(f"Start date {start} is after end date {end}.")

            if not client.class_exists(settings.class_name):
                print(
                    f"Warning: class '{settings.class_name}' was not found in the class list. "
                    "The absence payload will still be checked.",
                    file=sys.stderr,
                )

            print(f"Fetching WebUntis absences from {start} to {end} …")
            absences = client.absences(start, end)

            # Diagnostic: show exactly one raw absence record without triggering
            # convenience properties such as absence.name, which may call getStudents().
            try:
                first = next(iter(absences))
            except StopIteration:
                first = None

            if first is not None:
                print("\n=== FIRST RAW ABSENCE (DIAGNOSTIC) ===")
                pprint(getattr(first, "_data", {}), sort_dicts=True)
                print("=== END RAW ABSENCE ===\n")

            rows, saw_class_metadata = aggregate_absences(absences, settings.class_name)

            if not saw_class_metadata:
                print(
                    "WARNING: This WebUntis server did not expose class/group metadata in the "
                    "absence payload. The result may contain every absence visible to this account. "
                    "Check the CSV before relying on it.",
                    file=sys.stderr,
                )

            output = Path("reports") / f"{settings.class_name}_{start}_{end}.csv"
            write_csv(rows, output)

            print()
            print(f"Class:  {settings.class_name}")
            print(f"Period: {start} – {end}")
            print(f"Students with absence entries: {len(rows)}")
            print(f"Report: {output}")
            print()

            if rows:
                print(f"{'Name':32} {'exc.':>7} {'unexc.':>8} {'unclear':>8} {'total':>8}")
                print("-" * 70)
                for row in rows:
                    print(
                        f"{row.name[:32]:32} "
                        f"{row.excused_minutes:7} "
                        f"{row.unexcused_minutes:8} "
                        f"{row.unknown_minutes:8} "
                        f"{row.total_minutes:8}"
                    )
            else:
                print("No matching absence entries found.")

        return 0

    except webuntis.errors.BadCredentialsError:
        print(
            "Login failed. Username/password authentication was rejected by WebUntis. "
            "If your school requires 2FA/SSO, the next step is App/QR authentication.",
            file=sys.stderr,
        )
        return 3
    except webuntis.errors.Error as exc:
        print(f"WebUntis error: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
