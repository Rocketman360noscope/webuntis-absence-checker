from __future__ import annotations

from pathlib import Path
import sys

from browser_replay import BrowserReplayError, replay_browser_request


def main() -> int:
    try:
        curl_path = Path("curl.txt")
        print("Replaying the working Firefox WebUntis absence request from local curl.txt …")
        status, page = replay_browser_request(curl_path)

        print(f"HTTP status: {status}")
        if status != 200:
            print("Browser replay failed. The captured WebUntis session may have expired.", file=sys.stderr)
            return 4

        output_dir = Path("reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / "browser_replay.html"
        output.write_text(page, encoding="utf-8")

        print(f"Saved response: {output}")
        print(f"Response size: {len(page):,} characters")

        markers = {
            "SG8B": "SG8B" in page,
            "Fehlstunden": "Fehlstunden" in page,
            "Schüler*innen": "Schüler*innen" in page or "Schüler" in page,
        }
        print("Checks:")
        for name, present in markers.items():
            print(f"  {name}: {'YES' if present else 'NO'}")

        if all(markers.values()):
            print("\nSUCCESS: The browser-only absence page can be replayed from Python.")
        else:
            print("\nThe request returned HTML, but it may not be the expected absence table.")

        return 0

    except BrowserReplayError as exc:
        print(f"Browser replay setup error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
