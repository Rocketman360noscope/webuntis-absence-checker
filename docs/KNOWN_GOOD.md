# Verified working versions

This document records versions that were tested successfully with the GHSE WebUntis account. It contains no passwords, TOTP secrets, session data or student data.

## Primary rollback point

Branch: `known-good-2026-07-30-full-fetch`

Commit: `7faa4a918d2c1fa00dfeeedadd27cbdf9b2363e6`

Verified result on 2026-07-30:

- Chromium login completed with the dedicated browser 2FA secret.
- The full configured school-year range was requested.
- 2054 browser rows were parsed in total.
- 2053 rows belonged to SG8B.
- One SG8A row was excluded.
- 425 student-date groups were generated.
- Detail, daily and summary CSV files were created successfully.
- Login protection used at most one password attempt and one 2FA attempt.

The branch is intentionally kept unchanged so that a ZIP of this exact working state can be downloaded later.

## Important working milestones

### Direct authenticated absence request

Commit: `14dabd2d3f625c6674e47679fc2cb48f5fb6d836`

This version bypassed the WebUntis date widget and successfully requested the full school-year range through the authenticated Chromium session.

### Class filtering and daily report

Commit: `4e92a62c2fc3cb6b7c49be4ed896b71f474c93dd`

This version filtered the parsed rows to the configured class and generated the daily student-date report.

### Guarded browser login

Commit: `7faa4a918d2c1fa00dfeeedadd27cbdf9b2363e6`

This version used the single-attempt login guard and stopped instead of repeatedly submitting rejected credentials or 2FA codes.

## Development after the rollback point

The main branch may add dashboards, change tracking, scheduling and other features. The known-good branch must not be moved or modified.

Generated files in `reports/`, `.env`, browser HTML and snapshots contain sensitive information and must remain local. They are ignored by Git.
