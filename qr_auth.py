from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import pyotp
import requests


class QRLoginError(RuntimeError):
    pass


def parse_qr_uri(qr_uri: str) -> tuple[str, str, str, str]:
    """Return (server, school, username, secret) from an untis://setschool URI."""
    parsed = urlparse(qr_uri.strip())
    if parsed.scheme != "untis":
        raise QRLoginError("QR data does not start with 'untis://'.")

    params = parse_qs(parsed.query)

    def one(name: str) -> str:
        values = params.get(name)
        if not values or not values[0]:
            raise QRLoginError(f"QR data is missing '{name}'.")
        return values[0]

    raw_url = one("url")
    school = one("school")
    username = one("user")
    secret = one("key")

    server = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}").netloc
    if not server:
        server = raw_url.strip("/")

    return server, school, username, secret


def otp_login_with_secret(
    server: str,
    school: str,
    username: str,
    secret: str,
    useragent: str,
) -> tuple[str, requests.Session]:
    """Login using WebUntis app credentials and return JSESSIONID + HTTP session.

    The getUserData2017 result is retained on the requests session as
    ``webuntis_user_data``. This response can contain master data that lets us
    resolve element IDs without calling the legacy getStudents() method.
    """
    otp = pyotp.TOTP(secret.replace(" ", "")).now()
    client_time = int(time.time() * 1000)

    http = requests.Session()
    http.headers.update(
        {
            "User-Agent": useragent,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
        }
    )

    response = http.post(
        f"https://{server}/WebUntis/jsonrpc_intern.do",
        params={"m": "getUserData2017", "school": school, "v": "i2.2"},
        json={
            "id": useragent,
            "method": "getUserData2017",
            "params": [
                {
                    "auth": {
                        "clientTime": client_time,
                        "user": username,
                        "otp": otp,
                    }
                }
            ],
            "jsonrpc": "2.0",
        },
        timeout=30,
    )
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        raise QRLoginError("WebUntis returned an invalid response during app login.") from exc

    if payload.get("error"):
        message = payload["error"].get("message", "unknown error")
        raise QRLoginError(f"App login failed: {message}")

    # Keep the already-returned user/master data. requests.Session permits custom
    # attributes, and this avoids making another authenticated request.
    http.webuntis_user_data = payload.get("result")  # type: ignore[attr-defined]

    jsessionid = http.cookies.get("JSESSIONID")
    if not jsessionid:
        raise QRLoginError("App login did not return a JSESSIONID.")

    return jsessionid, http


def otp_login(qr_uri: str, useragent: str) -> tuple[str, str, str, str, requests.Session]:
    """Login from the complete WebUntis QR URI."""
    server, school, username, secret = parse_qr_uri(qr_uri)
    jsessionid, http = otp_login_with_secret(server, school, username, secret, useragent)
    return server, school, username, jsessionid, http
