import httpx
import pytest

from sentinel import store
from sentinel.models import Finding, RepoSettings, ScanEvent, ScannerFailure, TriagedIssue
from sentinel.store import Store, StoreError

FINDING = Finding(tool="semgrep", rule_id="r", severity="ERROR", message="m", file="app.py", line=5)
ISSUE = TriagedIssue(title="SQLi", severity="high", false_positive=False, explanation="e", fix="f",
                     findings=[FINDING, FINDING], review_reasons=["AI lowered severity"])


class FakeSupabase:
    def __init__(self, responses=None, status=200):
        self.calls, self.responses, self.status = [], responses or {}, status

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        self.calls.append({"method": method, "url": url, "params": params, "json": json, "headers": headers})
        body = self.responses.get((method, url.rsplit("/", 1)[1]), [])
        return httpx.Response(self.status, json=body, request=httpx.Request(method, url))


@pytest.fixture
def fake(monkeypatch):
    fake = FakeSupabase(responses={("GET", "repos"): [{"id": 1}], ("POST", "scans"): [{"id": 42}]})
    monkeypatch.setattr(store.httpx, "request", fake.request)
    return fake


def test_the_secret_key_goes_in_the_apikey_header_only(fake):
    Store("https://x.supabase.co/", "sb_secret_abc").repo_id("o/r")
    call = fake.calls[0]
    assert call["url"] == "https://x.supabase.co/rest/v1/repos"
    assert call["headers"]["apikey"] == "sb_secret_abc"
    assert "sb_secret_abc" not in call["url"] and "Authorization" not in call["headers"]


def test_repo_lookup_and_scan_start(fake):
    s = Store("https://x.supabase.co", "k")
    assert s.repo_id("o/r") == 1
    assert fake.calls[0]["params"] == {"full_name": "eq.o/r", "select": "id"}
    assert s.start_scan(1, 7, "a" * 40) == 42
    assert fake.calls[1]["json"] == {"repo_id": 1, "pr": 7, "head_sha": "a" * 40}
    assert fake.calls[1]["headers"]["Prefer"] == "return=representation"


def test_unknown_repo_is_none(monkeypatch):
    monkeypatch.setattr(store.httpx, "request", FakeSupabase().request)
    assert Store("https://x.supabase.co", "k").repo_id("o/r") is None


def test_finish_writes_issues_then_closes_the_scan(fake):
    Store("https://x.supabase.co", "k").finish_scan(42, [ISSUE], [ScannerFailure(scanner="trivy", error="Timeout")])
    issues, scan = fake.calls
    assert issues["method"] == "POST" and issues["json"][0]["scan_id"] == 42
    assert issues["json"][0]["findings"][0]["rule_id"] == "r" and issues["json"][0]["review_reasons"] == ["AI lowered severity"]
    assert scan["method"] == "PATCH" and scan["params"] == {"id": "eq.42"}
    assert (scan["json"]["status"], scan["json"]["finding_count"], scan["json"]["failed_scanners"]) == ("done", 2, ["trivy"])


def test_an_error_names_the_table_but_not_the_key(monkeypatch):
    monkeypatch.setattr(store.httpx, "request", FakeSupabase(status=401).request)
    with pytest.raises(StoreError, match="GET repos failed \\(401\\)") as e:
        Store("https://x.supabase.co", "sb_secret_abc").repo_id("o/r")
    assert "sb_secret_abc" not in str(e.value)


def test_pending_approvals_only_asks_for_fixes_still_waiting(fake):
    Store("https://x.supabase.co", "k").pending_approvals()
    call = fake.calls[0]
    assert call["url"].endswith("/rest/v1/approvals")
    assert call["params"]["fixes.status"] == "eq.waiting" and "fixes!inner(status)" in call["params"]["select"]


def test_user_login_reads_the_github_name(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["url"] = url
        return httpx.Response(200, json={"user_metadata": {"user_name": "dhiasalah"}}, request=httpx.Request("GET", url))

    monkeypatch.setattr(store.httpx, "get", fake_get)
    assert Store("https://x.supabase.co", "k").user_login("b734c29e-2684-435a-b0b3-195147dd7708") == "dhiasalah"
    assert seen["url"] == "https://x.supabase.co/auth/v1/admin/users/b734c29e-2684-435a-b0b3-195147dd7708"


def test_an_event_is_written_without_empty_fields(fake):
    s = Store("https://x.supabase.co", "k")
    s.add_event(42, ScanEvent(stage="scanner", status="ok", scanner="semgrep", count=9))
    s.add_event(42, ScanEvent(stage="checkout", status="started"))
    assert fake.calls[0]["json"] == {"scan_id": 42, "stage": "scanner", "status": "ok", "scanner": "semgrep", "count": 9}
    assert fake.calls[1]["json"] == {"scan_id": 42, "stage": "checkout", "status": "started"}


def test_no_settings_row_means_defaults(monkeypatch):
    monkeypatch.setattr(store.httpx, "request", FakeSupabase().request)
    assert Store("https://x.supabase.co", "k").repo_settings(1) == RepoSettings()


def test_settings_row_is_parsed_and_a_bad_one_raises(monkeypatch):
    row = {"scanners": ["semgrep"], "report_min_severity": "high", "llm_order": ["groq", "gemini"]}
    monkeypatch.setattr(store.httpx, "request", FakeSupabase(responses={("GET", "repo_settings"): [row]}).request)
    assert Store("https://x.supabase.co", "k").repo_settings(1).scanners == ["semgrep"]
    bad = {**row, "scanners": ["semgrep", "rm -rf"]}
    monkeypatch.setattr(store.httpx, "request", FakeSupabase(responses={("GET", "repo_settings"): [bad]}).request)
    with pytest.raises(ValueError):
        Store("https://x.supabase.co", "k").repo_settings(1)
