from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile


class BrowserReplayError(RuntimeError):
    pass


def replay_browser_request(path: Path) -> tuple[int, str]:
    """Execute Firefox's copied Windows cURL command unchanged via cmd.exe.

    This deliberately avoids reparsing Firefox/cmd escaping. The raw copied
    command is written to a temporary .cmd file and executed exactly as Windows
    would execute it in a console. stdout is captured as the HTML response.
    """
    if not path.exists():
        raise BrowserReplayError(
            f"Missing {path}. Copy the working Firefox POST as cURL into this file first."
        )

    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise BrowserReplayError(f"{path} is empty.")

    marker = "__WEBUNTIS_HTTP_STATUS__"
    command = text.rstrip() + f' -w "\\n{marker}:%{{http_code}}\\n"\n'

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".cmd",
        delete=False,
        newline="\r\n",
    ) as handle:
        cmd_path = Path(handle.name)
        handle.write("@echo off\n")
        handle.write(command)

    try:
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", str(cmd_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BrowserReplayError("Browser replay timed out after 90 seconds.") from exc
    finally:
        try:
            cmd_path.unlink(missing_ok=True)
        except OSError:
            pass

    output = completed.stdout
    status = 0
    marker_text = f"{marker}:"
    if marker_text in output:
        html, status_part = output.rsplit(marker_text, 1)
        output = html.rstrip("\r\n")
        first_line = status_part.strip().splitlines()[0] if status_part.strip() else ""
        try:
            status = int(first_line)
        except ValueError:
            status = 0

    if completed.returncode != 0 and not output:
        stderr = completed.stderr.strip()
        raise BrowserReplayError(
            f"curl replay failed with exit code {completed.returncode}: {stderr or 'unknown error'}"
        )

    return status, output
