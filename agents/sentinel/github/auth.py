import time
from pathlib import Path

import httpx
import jwt

GITHUB_API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def load_private_key(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def make_app_jwt(app_id: int, private_key_pem: str, now: int | None = None) -> str:
    now = int(time.time()) if now is None else now
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": str(app_id)}
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def get_app_info(app_jwt: str) -> dict:
    resp = httpx.get(
        f"{GITHUB_API}/app",
        headers={**HEADERS, "Authorization": f"Bearer {app_jwt}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
