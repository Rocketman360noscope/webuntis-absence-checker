from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import requests


class BrowserReplayError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserRequest:
    url: str
    headers: dict[str, str]
    body: str


def _dequote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def parse_firefox_windows_curl(path: Path) -> BrowserRequest:
    """Parse Firefox's Windows/cmd 'Copy as cURL' output without exposing secrets.

    Firefox escapes many cmd metacharacters with ^. For the captured WebUntis
    request those carets are shell escaping, not part of the actual HTTP values.
    """
    if not path.exists():
        raise BrowserReplayError(f"Missing {path}. Copy the working Firefox POST as cURL into this file first.")

    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise BrowserReplayError(f"{path} is empty.")

    normalized = text.replace("^\r\n", " ").replace("^\n", " ").replace("^", "")

    url_match = re.search(r"\bcurl(?:\.exe)?\s+(\"[^\"]+\"|\S+)", normalized, flags=re.IGNORECASE)
    if not url_match:
        raise BrowserReplayError("Could not find the cURL request URL in curl.txt.")
    url = _dequote(url_match.group(1))

    headers: dict[str, str] = {}
    for raw_header in re.findall(r"(?:^|\s)-H\s+\"([^\"]+)\"", normalized, flags=re.IGNORECASE):
        if ":" not in raw_header:
            continue
        name, value = raw_header.split(":", 1)
        headers[name.strip()] = value.strip()

    body_match = re.search(r"--data(?:-raw)?\s+\"([^\"]*)\"", normalized, flags=re.IGNORECASE)
    if not body_match:
        raise BrowserReplayError("Could not find --data-raw form data in curl.txt.")
    body = body_match.group(1)

    if "Cookie" not in headers and "cookie" not in {k.casefold() for k in headers}:
        raise BrowserReplayError("The copied request does not contain a Cookie header.")

    return BrowserRequest(url=url, headers=headers, body=body)


def replay_browser_request(path: Path) -> tuple[int, str]:
    request = parse_firefox_windows_curl(path)

    # Let requests calculate transport-specific headers itself.
    blocked = {"host", "content-length", "connection"}
    headers = {k: v for k, v in request.headers.items() if k.casefold() not in blocked}

    response = requests.post(
        request.url,
        headers=headers,
        data=request.body,
        timeout=60,
    )
    return response.status_code, response.text
