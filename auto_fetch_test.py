from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

from absence_html_parser import parse_absence_rows, write_detail_csv, write_summary_csv
from browser_automation import BrowserAutomationError, fetch_absence_html_browser
from config import load_settings


def _default_schoolyear_range(today: date) -> tuple[date, date]:
    """Return a practical school-year range without using the legacy API.

    WebUntis itself restricts the submitted range to the current school year.
    START_DATE and END_DATE in .env still override these defaults.
    """
    start_year = today.year if today.month >= 8 else today.year - 1
    return date(start_year, 9, 1), today


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

        page = fetch_absence_html_browser(settings, start, end, headless=False)

        rows = parse_absence_rows(page)
        output_dir = Path("reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        html_output = output_dir / "browser_auto_response.html"
        detail_output = output_dir / "SG8B_absences_detail_auto.csv"
        summary_output = output_dir / "SG8B_absences_summary_auto.csv"

        html_output.write_text(page, encoding="utf-8")
        write_detail_csv(rows, detail_output)
        write_summary_csv(rows, summary_output)

        print()
        print("SUCCESS: Fully automatic browser fetch worked.")
        print(f"Parsed absence rows: {len(rows)}")
        print(f"Detail CSV:  {detail_output}")
        print(f"Summary CSV: {summary_output}")
        return 0

    except BrowserAutomationError as exc:
        print(f"AUTOMATION STOPPED: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
