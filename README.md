# WebUntis Absence Checker

Small Python tool for retrieving WebUntis absence data for a date range and exporting a class report as CSV.

The first version intentionally uses the documented `python-webuntis` username/password API flow. If the school's WebUntis rejects this because of 2FA/SSO, the code is structured so App/QR authentication can be added next without changing the reporting layer.

## What it does

- logs in to WebUntis
- automatically uses the start of the current WebUntis school year unless `START_DATE` is configured
- fetches absences up to today (or `END_DATE`)
- tries to restrict the data to the configured class, default `SG8B`
- totals excused, unexcused and unclear absence minutes per student
- writes a semicolon-separated CSV into `reports/`

> Important: WebUntis installations return slightly different payloads. If your server does not expose class/group metadata with absences, the program prints a prominent warning instead of pretending the filtering is reliable.

## Setup on Windows

Open PowerShell in the project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Then edit `.env` and enter your WebUntis values.

Never paste your real password, OTP secret, QR secret, or `.env` file into GitHub. `.env` is excluded by `.gitignore`.

## Configuration

```env
WEBUNTIS_SERVER=your-school.webuntis.com
WEBUNTIS_SCHOOL=your-school-name
WEBUNTIS_USERNAME=your-username
WEBUNTIS_PASSWORD=your-password
WEBUNTIS_USERAGENT=webuntis-absence-checker
WEBUNTIS_CLASS=SG8B
START_DATE=
END_DATE=
```

Dates use `YYYY-MM-DD`. When `START_DATE` is blank, the checker asks WebUntis for the current school year and uses its first day.

## Run

```powershell
py app.py
```

A successful run creates a file such as:

```text
reports/SG8B_2025-09-01_2026-07-27.csv
```

The generated report directory is ignored by Git so student names and attendance data are not accidentally committed.

## About 2FA

`python-webuntis` currently authenticates through the legacy JSON-RPC username/password method. It does not implement a TOTP field in that login call. Therefore the first useful test is simply running this version against the school's account.

If WebUntis responds with `bad credentials` even though the credentials are correct in the browser, do **not** disable 2FA. The next implementation step is App/QR-token authentication instead.

## Current limitations

WebUntis absence records can contain duplicates when multiple groups/teachers overlap; `python-webuntis` notes that usually only one of those entries carries the actual `absentTime`, so this checker totals the supplied absence minutes rather than simply counting rows.

Excuse-status strings may also differ by WebUntis configuration. Unknown statuses are deliberately kept in a separate `Unklar` column so data is not silently misclassified.
