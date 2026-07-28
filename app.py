from __future__ import annotations

from datetime import date
from pathlib import Path
import re
import sys

import webuntis

from config import load_settings
from webuntis_client import WebUntisClient


def _html_to_text(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


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

            print(
                f"Fetching browser-style WebUntis absence page for {settings.class_name} "
                f"from {start} to {end} …"
            )
            page = client.browser_absence_times_html(start, end, settings.class_id)

            output_dir = Path("reports")
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / f"{settings.class_name}_{start}_{end}_browser.html"
            output.write_text(page, encoding="utf-8")

            text = _html_to_text(page)
            print()
            print("Browser request succeeded.")
            print(f"Saved response: {output}")
            print(f"Response size: {len(page):,} characters")
            print()
            print("=== RESPONSE PREVIEW ===")
            print(text[:1800])
            print("=== END PREVIEW ===")

        return 0

    except webuntis.errors.BadCredentialsError:
        print("Login failed.", file=sys.stderr)
        return 3
    except webuntis.errors.Error as exc:
        print(f"WebUntis error: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
