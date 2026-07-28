from __future__ import annotations

from datetime import date
import sys

import webuntis

from config import load_settings
from webuntis_client import WebUntisClient


def _describe(value: object, path: str = "result", depth: int = 0) -> None:
    """Print structure only, not full personal data."""
    if depth > 4:
        return

    indent = "  " * depth
    if isinstance(value, dict):
        keys = list(value.keys())
        print(f"{indent}{path}: dict keys={keys}")
        for key, child in value.items():
            key_lower = str(key).casefold()
            # Prioritize containers likely to hold master/student data.
            if depth < 2 or any(word in key_lower for word in ("master", "student", "element", "class", "klasse")):
                _describe(child, f"{path}.{key}", depth + 1)
    elif isinstance(value, list):
        print(f"{indent}{path}: list length={len(value)}")
        if value:
            first = value[0]
            if isinstance(first, dict):
                print(f"{indent}  first item keys={list(first.keys())}")
                # Show only ID/name-like fields from the first item, never secrets/tokens.
                safe = {
                    k: v
                    for k, v in first.items()
                    if any(word in str(k).casefold() for word in ("id", "name", "class", "klasse", "type"))
                }
                if safe:
                    print(f"{indent}  first item safe fields={safe}")
    else:
        # Avoid printing arbitrary scalar values from the login payload.
        print(f"{indent}{path}: {type(value).__name__}")


def main() -> int:
    try:
        settings = load_settings()
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        with WebUntisClient(settings) as client:
            print("App login succeeded.")
            print()
            print("=== getUserData2017 STRUCTURE ===")
            user_data = getattr(client.http, "webuntis_user_data", None) if client.http else None
            if user_data is None:
                print("No getUserData2017 result was retained.")
            else:
                _describe(user_data)
            print("=== END STRUCTURE ===")

            schoolyear_start, schoolyear_end = client.current_schoolyear_dates()
            start = settings.start_date or schoolyear_start
            end = settings.end_date or min(date.today(), schoolyear_end)
            print()
            print(f"School year range available: {start} to {end}")

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
