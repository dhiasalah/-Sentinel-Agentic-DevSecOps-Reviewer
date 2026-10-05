from contextlib import contextmanager

import pytest

from sentinel import fix_graph, fix_requests
from sentinel.fix_requests import run_fix_request
from sentinel.fixer import FixError, NotFixable, Patch
from sentinel.llm.providers import ProviderUnavailable
from sentinel.llm.router import AllProvidersFailed
from sentinel.models import Finding, RepoSettings
from sentinel.sandbox import Verification

FINDING = {"tool": "semgrep", "rule_id": "sqli", "severity": "ERROR", "message": "m", "file": "app.py", "line": 5}
OTHER = {**FINDING, "rule_id": "xss", "line": 9}
REQUEST = {
    "id": 3,
    "issue": {
        "title": "SQL injection", "severity": "high", "false_positive": False, "explanation": "e", "fix": "f",
        "review_reasons": [], "findings": [FINDING],
        "scan": {"id": 12, "repo_id": 1, "pr": 7, "head_sha": "a" * 40, "repo": {"full_name": "o/r"}},
    },
}
PATCH = Patch(summary="use parameters", diff="--- a/app.py\n+++ b/app.py\n", provider="fake")


class FakeStore:
    def __init__(self, request=REQUEST, claim=True):
        self.request, self.claim = request, claim
        self.saved, self.finished, self.claimed = [], [], []

    def next_fix_request(self):
        return self.request

    def claim_fix_request(self, request_id):
        self.claimed.append(request_id)
        return self.claim

    def scan_findings(self, scan_id):
        assert scan_id == 12
        return [FINDING, OTHER]

    def repo_settings(self, repo_id):
        return RepoSettings(llm_order=["groq", "gemini"])

    def save_fix(self, fix):
        self.saved.append(fix)

    def finish_fix_request(self, request_id, status, fix_id=None, reason=None):
        self.finished.append((request_id, status, fix_id, reason))


@pytest.fixture
def checked_out(monkeypatch, tmp_path):
    seen = {}

    @contextmanager
    def checkout(repo, sha, settings):
        seen["at"] = (repo, sha)
        yield tmp_path

    monkeypatch.setattr(fix_requests, "checkout_commit", checkout)
    monkeypatch.setattr(fix_requests, "build_router", lambda settings, order: seen.setdefault("order", list(order)))
    monkeypatch.setattr(fix_graph, "verify_fix", lambda *a: Verification(changed=["app.py"], scanners=["semgrep"]))
    return seen


def run(store, tmp_path):
    return run_fix_request(store, tmp_path / "a.sqlite", settings=None)


def test_a_request_becomes_a_fix_waiting_for_a_human(checked_out, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(fix_graph, "propose_fix", lambda issue, path, router, all_findings: calls.append(
        (issue.title, len(all_findings))) or PATCH)
    store = FakeStore()
    assert run(store, tmp_path)
    assert checked_out == {"at": ("o/r", "a" * 40), "order": ["groq", "gemini"]}
    assert calls == [("SQL injection", 2)]
    [fix] = store.saved
    assert fix["status"] == "waiting" and fix["pr"] == 7 and fix["head_sha"] == "a" * 40 and fix["repo_id"] == 1
    assert store.finished == [(3, "waiting", fix["id"], None)]


def test_a_refused_fix_is_recorded_without_a_fix_row(checked_out, monkeypatch, tmp_path):
    def refuse(*a):
        raise NotFixable("leaked secrets must be rotated by a human", "secret")
    monkeypatch.setattr(fix_graph, "propose_fix", refuse)
    store = FakeStore()
    run(store, tmp_path)
    assert store.saved == [] and store.finished == [(3, "refused", None, "secret")]


def test_a_crash_marks_the_request_failed_so_it_can_be_retried(checked_out, monkeypatch, tmp_path):
    def boom(*a):
        raise RuntimeError("GitHub refused the token")
    monkeypatch.setattr(fix_graph, "propose_fix", boom)
    store = FakeStore()
    assert run(store, tmp_path)
    assert store.finished == [(3, "failed", None, "error")]


@pytest.mark.parametrize("errors, reason", [
    ([ProviderUnavailable("429"), ProviderUnavailable("413")], "ai_unavailable"),
    ([ProviderUnavailable("429"), FixError("edit is more than 10 lines away")], "ai_bad_answer"),
])
def test_ai_failures_say_whether_the_ai_was_busy_or_wrong(checked_out, monkeypatch, tmp_path, errors, reason):
    def fail(*a):
        raise AllProvidersFailed("all failed", errors)
    monkeypatch.setattr(fix_graph, "propose_fix", fail)
    store = FakeStore()
    run(store, tmp_path)
    assert store.finished == [(3, "failed", None, reason)]


def test_a_sandbox_failure_says_what_went_wrong(checked_out, monkeypatch, tmp_path):
    monkeypatch.setattr(fix_graph, "propose_fix", lambda *a: PATCH)
    monkeypatch.setattr(fix_graph, "verify_fix", lambda *a: Verification(
        changed=["app.py"], scanners=["semgrep"], new=[Finding.model_validate(OTHER)]))
    store = FakeStore()
    run(store, tmp_path)
    assert store.finished == [(3, "not_verified", None, "new_findings")]


def test_nothing_queued_does_nothing(tmp_path):
    store = FakeStore(request=None)
    assert not run(store, tmp_path)
    assert store.claimed == [] and store.finished == []


def test_a_request_another_worker_took_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(fix_requests, "propose", lambda *a: pytest.fail("must not run"))
    store = FakeStore(claim=False)
    assert not run(store, tmp_path)
    assert store.finished == []
