from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
import re
import sys

from bs4 import BeautifulSoup

from absence_html_parser import (
    parse_absence_rows,
    write_daily_csv,
    write_detail_csv,
    write_summary_csv,
)
from browser_automation import BrowserAutomationError
from browser_automation_v2 import fetch_absence_html_browser_v2
from change_tracking import (
    compare_rows,
    load_snapshot,
    safe_change_summary,
    save_snapshot,
    write_changes_csv,
)
from config import load_settings


def _default_schoolyear_range(today: date) -> tuple[date, date]:
    """Return a practical school-year range without using the legacy API.

    WebUntis itself restricts the submitted range to the current school year.
    START_DATE and END_DATE in .env still override these defaults.
    """
    start_year = today.year if today.month >= 8 else today.year - 1
    return date(start_year, 9, 1), today


def _print_safe_diagnostics(page: str, class_name: str) -> None:
    """Print structural information without exposing student names or notes."""
    soup = BeautifulSoup(page, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    date_hits = re.findall(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", page_text)

    print("Response diagnostics:")
    print(f"  HTML characters: {len(page)}")
    print(f"  Tables: {len(soup.find_all('table'))}")
    print(f"  Table rows: {len(soup.find_all('tr'))}")
    print(f"  Table cells: {len(soup.find_all('td'))}")
    print(f"  Date values found: {len(date_hits)}")
    print(f"  Contains class name: {'YES' if class_name in page else 'NO'}")
    print(f"  Contains 'Keine Daten': {'YES' if 'Keine Daten' in page_text else 'NO'}")
    print(f"  Contains 'Keine Einträge': {'YES' if 'Keine Einträge' in page_text else 'NO'}")
    print(f"  Contains 'Fehlstunden': {'YES' if 'Fehlstunden' in page_text else 'NO'}")
    print(f"  Contains 'Nichts anzuzeigen': {'YES' if 'Nichts anzuzeigen' in page_text else 'NO'}")


def main() -> int:
    try:
        settings = load_settings()

        default_start, default_end = _default_schoolyear_range(date.today())
        start = settings.start_date or default_start
        end = settings.end_date or default_end

        print("=== AUTOMATIC BROWSER TEST ===")
        print(f"Class: {settings.class_name} ({settings.class_id})")
        print(f"Range: {start} to {end}")
        print("A Chromium window will open. Do not type anything unless the test stops with an error.")
        print()

        page = fetch_absence_html_browser_v2(settings, start, end, headless=False)

        output_dir = Path("reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        html_output = output_dir / "browser_auto_response.html"
        detail_output = output_dir / f"{settings.class_name}_absences_detail_auto.csv"
        daily_output = output_dir / f"{settings.class_name}_absences_daily_auto.csv"
        summary_output = output_dir / f"{settings.class_name}_absences_summary_auto.csv"
        changes_output = output_dir / f"{settings.class_name}_absence_changes_latest.csv"
        snapshot_output = output_dir / f"{settings.class_name}_absence_snapshot.json"

        # Always preserve the fetched response before parsing. This remains local
        # and is ignored by Git because it can contain sensitive student data.
        html_output.write_text(page, encoding="utf-8")
        print(f"Fetched HTML saved locally: {html_output}")
        _print_safe_diagnostics(page, settings.class_name)

        try:
            parsed_rows = parse_absence_rows(page)
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc} The raw response was saved locally as {html_output}."
            ) from exc

        foreign_classes = Counter(
            row.class_name for row in parsed_rows if row.class_name != settings.class_name
        )
        rows = [row for row in parsed_rows if row.class_name == settings.class_name]
        if not rows:
            raise RuntimeError(
                f"Absence rows were parsed, but none belonged to configured class {settings.class_name}."
            )

        previous_snapshot = load_snapshot(snapshot_output)

        write_detail_csv(rows, detail_output)
        daily_count = write_daily_csv(rows, daily_output)
        write_summary_csv(rows, summary_output)

        if previous_snapshot is None:
            changes = []
            comparison_message = (
                "No previous snapshot existed. The current data was stored as the comparison baseline."
            )
        else:
            changes = compare_rows(previous_snapshot, rows)
            comparison_message = f"Changes since previous successful run: {len(changes)}"

        write_changes_csv(changes, changes_output)
        # Save the new baseline only after all report files were written successfully.
        save_snapshot(rows, snapshot_output)

        print()
        print("SUCCESS: Fully automatic browser fetch worked.")
        print(f"Parsed rows for {settings.class_name}: {len(rows)}")
        print(f"Student-date groups: {daily_count}")
        if foreign_classes:
            excluded = sum(foreign_classes.values())
            classes = ", ".join(f"{name}: {count}" for name, count in sorted(foreign_classes.items()))
            print(f"Excluded rows outside {settings.class_name}: {excluded} ({classes})")
        print(comparison_message)
        if changes:
            change_counts = safe_change_summary(changes)
            print(
                "Change types: "
                + ", ".join(
                    f"{name}: {count}" for name, count in sorted(change_counts.items())
                )
            )
        print(f"Detail CSV:  {detail_output}")
        print(f"Daily CSV:   {daily_output}")
        print(f"Summary CSV: {summary_output}")
        print(f"Changes CSV: {changes_output}")
        print(f"Snapshot:    {snapshot_output}")
        return 0

    except BrowserAutomationError as exc:
        print(f"AUTOMATION STOPPED: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
