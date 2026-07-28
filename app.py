from __future__ import annotations

from pathlib import Path
import sys

from absence_html_parser import parse_absence_rows, write_detail_csv, write_summary_csv
from browser_replay import BrowserReplayError, replay_browser_request


def main() -> int:
    try:
        saved_response = Path("browser_response.html")
        if saved_response.exists():
            print("Using saved browser_response.html for parsing test …")
            page = saved_response.read_text(encoding="utf-8", errors="replace")
            status = 200
        else:
            curl_path = Path("curl.txt")
            print("Replaying the working Firefox WebUntis absence request from local curl.txt …")
            status, page = replay_browser_request(curl_path)

        print(f"HTTP status: {status}")
        if status not in (0, 200):
            print("Browser replay failed. The captured WebUntis session may have expired.", file=sys.stderr)
            return 4

        markers = {
            "SG8B": "SG8B" in page,
            "Fehlstunden": "Fehlstunden" in page,
            "Schüler*innen": "Schüler*innen" in page or "Schüler" in page,
        }
        print("Checks:")
        for name, present in markers.items():
            print(f"  {name}: {'YES' if present else 'NO'}")

        if not all(markers.values()):
            print("The response does not look like the expected absence page.", file=sys.stderr)
            return 5

        output_dir = Path("reports")
        output_dir.mkdir(parents=True, exist_ok=True)

        rows = parse_absence_rows(page)
        detail_output = output_dir / "SG8B_absences_detail.csv"
        summary_output = output_dir / "SG8B_absences_summary.csv"
        write_detail_csv(rows, detail_output)
        write_summary_csv(rows, summary_output)

        print()
        print("SUCCESS: WebUntis absence page parsed.")
        print(f"Parsed absence rows: {len(rows)}")
        print(f"Detail CSV:  {detail_output}")
        print(f"Summary CSV: {summary_output}")

        if rows:
            first = rows[0]
            print()
            print("First parsed row:")
            print(f"  Student: {first.student}")
            print(f"  Class:   {first.class_name}")
            print(f"  Date:    {first.date}")
            print(f"  Time:    {first.time}")
            print(f"  Subject: {first.subject}")
            print(f"  Reason:  {first.reason or '(empty)'}")
            print(f"  Status:  {first.status or '(empty)'}")

        return 0

    except BrowserReplayError as exc:
        print(f"Browser replay setup error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
