from datetime import datetime, timezone

import httpx

from sentinel.config import Settings
from sentinel.models import ScannerFailure, TriagedIssue


class StoreError(Exception):
    """Supabase refused or failed a request."""


class Store:
    """Writes scan results to Supabase through its REST API, with the secret key (bypasses RLS)."""

    def __init__(self, url: str, secret_key: str):
        self.base = f"{url.rstrip('/')}/rest/v1"
        self.headers = {"apikey": secret_key, "Content-Type": "application/json"}

    def _send(self, method: str, table: str, params: dict | None = None, json=None, returning: bool = False) -> list:
        headers = {**self.headers, "Prefer": "return=representation" if returning else "return=minimal"}
        resp = httpx.request(method, f"{self.base}/{table}", params=params, json=json, headers=headers, timeout=10)
        if resp.is_error:
            raise StoreError(f"Supabase {method} {table} failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json() if returning or method == "GET" else []

    def repo_id(self, full_name: str) -> int | None:
        rows = self._send("GET", "repos", params={"full_name": f"eq.{full_name}", "select": "id"})
        return rows[0]["id"] if rows else None

    def start_scan(self, repo_id: int, pr: int, head_sha: str) -> int:
        rows = self._send("POST", "scans", json={"repo_id": repo_id, "pr": pr, "head_sha": head_sha}, returning=True)
        return rows[0]["id"]

    def finish_scan(self, scan_id: int, issues: list[TriagedIssue], failures: list[ScannerFailure]) -> None:
        if issues:
            self._send("POST", "issues", json=[{
                "scan_id": scan_id,
                "severity": issue.severity,
                "title": issue.title,
                "explanation": issue.explanation,
                "fix": issue.fix,
                "false_positive": issue.false_positive,
                "review_reasons": issue.review_reasons,
                "findings": [f.model_dump() for f in issue.findings],
            } for issue in issues])
        self._send("PATCH", "scans", params={"id": f"eq.{scan_id}"}, json={
            "status": "done",
            "finding_count": sum(len(issue.findings) for issue in issues),
            "failed_scanners": sorted(f.scanner for f in failures),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })

    def fail_scan(self, scan_id: int) -> None:
        self._send("PATCH", "scans", params={"id": f"eq.{scan_id}"},
                   json={"status": "failed", "finished_at": datetime.now(timezone.utc).isoformat()})


def open_store(settings: Settings | None) -> Store | None:
    if settings is None or not settings.supabase_url or settings.supabase_secret_key is None:
        return None
    return Store(settings.supabase_url, settings.supabase_secret_key.get_secret_value())
