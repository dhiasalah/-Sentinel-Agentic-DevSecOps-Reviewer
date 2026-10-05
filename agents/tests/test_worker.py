import json

import fakeredis
import pytest

from sentinel import worker
from sentinel.models import Finding, RepoSettings, ScanEvent, ScannerFailure, TriagedIssue

SHA = "a" * 40
JOB = json.dumps({"delivery": "d-1", "repo": "o/r", "pr": 7, "head_sha": SHA, "installation_id": 99})


@pytest.fixture
def r():
    return fakeredis.FakeRedis()

@pytest.fixture(autouse=True)
def posted(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "post_report", lambda *args: calls.append(args[:2]) or "created")
    return calls



def lengths(r):
    return r.llen(worker.QUEUE), r.llen(worker.PROCESSING), r.llen(worker.DEAD)


def test_job_is_scanned_then_removed(r, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "scan_pr", lambda repo, sha, inst, settings, **kw: calls.append((repo, sha, inst)) or ([], []))
    r.lpush(worker.QUEUE, JOB)
    assert worker.process_one(r, settings=None, timeout=1)
    assert calls == [("o/r", SHA, 99)]
    assert lengths(r) == (0, 0, 0)


def test_failing_scan_goes_to_dead_letter(r, monkeypatch):
    def boom(*args, **kw):
        raise RuntimeError("git fetch failed")
    monkeypatch.setattr(worker, "scan_pr", boom)
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert lengths(r) == (0, 0, 1)


def test_malformed_job_is_never_scanned(r, monkeypatch):
    monkeypatch.setattr(worker, "scan_pr", lambda *a, **kw: pytest.fail("scan_pr must not run"))
    r.lpush(worker.QUEUE, json.dumps({"repo": "o/r"}))
    worker.process_one(r, settings=None, timeout=1)
    assert lengths(r) == (0, 0, 1)


def test_jobs_are_first_in_first_out(r, monkeypatch):
    seen = []
    monkeypatch.setattr(worker, "scan_pr", lambda repo, sha, inst, settings, **kw: seen.append(inst) or ([], []))
    for inst in (1, 2, 3):
        r.lpush(worker.QUEUE, JOB.replace("99", str(inst)))
    while worker.process_one(r, settings=None, timeout=1):
        pass
    assert seen == [1, 2, 3]


def test_unfinished_jobs_are_requeued_on_start(r):
    r.lpush(worker.PROCESSING, JOB)
    assert worker.requeue_stale(r) == 1
    assert lengths(r) == (1, 0, 0)


def test_report_is_posted_after_scan(r, monkeypatch, posted):
    monkeypatch.setattr(worker, "scan_pr", lambda *a, **kw: ([], []))
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert posted == [("o/r", 7)]


def test_failed_scan_posts_nothing(r, monkeypatch, posted):
    def boom(*args, **kw):
        raise RuntimeError("semgrep crashed")
    monkeypatch.setattr(worker, "scan_pr", boom)
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert posted == []


def test_partial_scan_still_posts_the_failure(r, monkeypatch):
    failure = ScannerFailure(scanner="semgrep", error="TimeoutExpired")
    sent = []
    monkeypatch.setattr(worker, "scan_pr", lambda *a, **kw: ([], [failure]))
    monkeypatch.setattr(worker, "post_report", lambda *args: sent.append(args) or "created")
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert sent[0][6] == [failure]
    assert lengths(r) == (0, 0, 0)


class FakeStore:
    def __init__(self, repo_id=1, broken=False, settings=None):
        self.repo, self.broken, self.calls, self.events = repo_id, broken, [], []
        self.settings = settings or RepoSettings()

    def repo_id(self, full_name):
        if self.broken:
            raise RuntimeError("supabase is down")
        return self.repo

    def start_scan(self, repo_id, pr, head_sha):
        self.calls.append(("start", repo_id, pr))
        return 42

    def finish_scan(self, scan_id, issues, failures):
        self.calls.append(("finish", scan_id, len(issues)))

    def fail_scan(self, scan_id):
        self.calls.append(("fail", scan_id))

    def repo_settings(self, repo_id):
        if isinstance(self.settings, Exception):
            raise self.settings
        return self.settings

    def add_event(self, scan_id, event):
        self.events.append((scan_id, event.stage, event.status))


def test_results_are_stored_for_a_linked_repo(r, monkeypatch, posted):
    fake = FakeStore()
    monkeypatch.setattr(worker, "open_store", lambda settings: fake)
    monkeypatch.setattr(worker, "scan_pr", lambda *a, **kw: ([], []))
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert fake.calls == [("start", 1, 7), ("finish", 42, 0)] and posted == [("o/r", 7)]


def test_a_failed_scan_is_marked_failed(r, monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(worker, "open_store", lambda settings: fake)
    monkeypatch.setattr(worker, "scan_pr", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("git fetch failed")))
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert fake.calls == [("start", 1, 7), ("fail", 42)] and lengths(r) == (0, 0, 1)


@pytest.mark.parametrize("fake", [FakeStore(repo_id=None), FakeStore(broken=True)])
def test_an_unlinked_repo_or_a_down_database_never_blocks_the_comment(r, monkeypatch, posted, fake):
    monkeypatch.setattr(worker, "open_store", lambda settings: fake)
    monkeypatch.setattr(worker, "scan_pr", lambda *a, **kw: ([], []))
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert fake.calls == [] and posted == [("o/r", 7)] and lengths(r) == (0, 0, 0)


def sev(severity):
    finding = Finding(tool="semgrep", rule_id="r", severity="INFO", message="m", file="a.py", line=1)
    return TriagedIssue(title=severity, severity=severity, false_positive=False, explanation="e", fix="f",
                        findings=[finding])


def test_owner_settings_reach_the_scan_and_the_threshold_trims_only_the_comment(r, monkeypatch):
    fake = FakeStore(settings=RepoSettings(scanners=["semgrep"], report_min_severity="high",
                                           llm_order=["groq", "gemini"]))
    seen, sent = {}, []

    def fake_scan(repo, sha, inst, settings, repo_settings=None, on_event=None):
        seen["settings"] = repo_settings
        return [sev("critical"), sev("high"), sev("low")], []

    monkeypatch.setattr(worker, "open_store", lambda settings: fake)
    monkeypatch.setattr(worker, "scan_pr", fake_scan)
    monkeypatch.setattr(worker, "post_report", lambda *args: sent.append(args) or "created")
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert seen["settings"].scanners == ["semgrep"] and seen["settings"].llm_order == ["groq", "gemini"]
    assert [i.severity for i in sent[0][4]] == ["critical", "high"] and sent[0][8] == 1
    assert fake.calls[-1] == ("finish", 42, 3)


def test_unreadable_settings_fall_back_to_scanning_everything(r, monkeypatch, posted):
    fake = FakeStore(settings=RuntimeError("repo_settings table missing"))
    seen = {}
    monkeypatch.setattr(worker, "open_store", lambda settings: fake)
    monkeypatch.setattr(worker, "scan_pr", lambda *a, repo_settings=None, **kw: seen.update(s=repo_settings) or ([], []))
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert seen["s"] == RepoSettings() and posted == [("o/r", 7)]


def test_progress_is_recorded_and_the_scan_closes_after_the_report(r, monkeypatch, posted):
    fake = FakeStore()

    def fake_scan(*args, on_event=None, **kw):
        on_event(ScanEvent(stage="plan", status="ok", count=2))
        return [], []

    monkeypatch.setattr(worker, "open_store", lambda settings: fake)
    monkeypatch.setattr(worker, "scan_pr", fake_scan)
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert fake.events == [(42, "plan", "ok"), (42, "report", "started"), (42, "report", "ok")]
    assert fake.calls[-1] == ("finish", 42, 0)


def test_progress_is_not_recorded_for_an_unlinked_repo(r, monkeypatch, posted):
    fake = FakeStore(repo_id=None)

    def fake_scan(*args, on_event=None, **kw):
        on_event(ScanEvent(stage="plan", status="ok"))
        return [], []

    monkeypatch.setattr(worker, "open_store", lambda settings: fake)
    monkeypatch.setattr(worker, "scan_pr", fake_scan)
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert fake.events == [] and posted == [("o/r", 7)]


def test_a_failed_comment_still_stores_the_results(r, monkeypatch):
    fake = FakeStore()

    def broken_post(*args):
        raise RuntimeError("github 502")

    monkeypatch.setattr(worker, "open_store", lambda settings: fake)
    monkeypatch.setattr(worker, "scan_pr", lambda *a, **kw: ([sev("high")], []))
    monkeypatch.setattr(worker, "post_report", broken_post)
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert fake.calls[-1] == ("finish", 42, 1) and (42, "report", "failed") in fake.events
    assert lengths(r) == (0, 0, 1)
