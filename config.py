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
    qr_uri: str
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

    qr_uri = (os.getenv("WEBUNTIS_QR_URI") or "").strip()
    server = (os.getenv("WEBUNTIS_SERVER") or "").strip()
    school = (os.getenv("WEBUNTIS_SCHOOL") or "").strip()
    username = (os.getenv("WEBUNTIS_USERNAME") or "").strip()
    password = os.getenv("WEBUNTIS_PASSWORD") or ""

    # QR authentication contains server/school/user itself. For the legacy
    # fallback, all four classic values are required.
    if not qr_uri:
        missing = [
            key
            for key, value in {
                "WEBUNTIS_SERVER": server,
                "WEBUNTIS_SCHOOL": school,
                "WEBUNTIS_USERNAME": username,
                "WEBUNTIS_PASSWORD": password,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing configuration: " + ", ".join(missing) +
                ". Add WEBUNTIS_QR_URI or fill in the classic login values."
            )

    return Settings(
        server=server,
        school=school,
        username=username,
        password=password,
        qr_uri=qr_uri,
        useragent=os.getenv("WEBUNTIS_USERAGENT", "webuntis-absence-checker"),
        class_name=os.getenv("WEBUNTIS_CLASS", "SG8B"),
        start_date=_parse_date(os.getenv("START_DATE")),
        end_date=_parse_date(os.getenv("END_DATE")),
    )
