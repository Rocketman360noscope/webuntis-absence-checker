from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    server: str
    school: str
    username: str
    password: str
    useragent: str
    class_name: str
    start_date: date | None
    end_date: date | None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def load_settings() -> Settings:
    load_dotenv()

    required = {
        "WEBUNTIS_SERVER": os.getenv("WEBUNTIS_SERVER"),
        "WEBUNTIS_SCHOOL": os.getenv("WEBUNTIS_SCHOOL"),
        "WEBUNTIS_USERNAME": os.getenv("WEBUNTIS_USERNAME"),
        "WEBUNTIS_PASSWORD": os.getenv("WEBUNTIS_PASSWORD"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing configuration: " + ", ".join(missing) +
            ". Copy .env.example to .env and fill in the values."
        )

    return Settings(
        server=required["WEBUNTIS_SERVER"] or "",
        school=required["WEBUNTIS_SCHOOL"] or "",
        username=required["WEBUNTIS_USERNAME"] or "",
        password=required["WEBUNTIS_PASSWORD"] or "",
        useragent=os.getenv("WEBUNTIS_USERAGENT", "webuntis-absence-checker"),
        class_name=os.getenv("WEBUNTIS_CLASS", "SG8B"),
        start_date=_parse_date(os.getenv("START_DATE")),
        end_date=_parse_date(os.getenv("END_DATE")),
    )
