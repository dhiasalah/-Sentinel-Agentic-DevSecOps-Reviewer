import json

import fakeredis
import pytest

from sentinel import worker
from sentinel.models import ScannerFailure

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
    monkeypatch.setattr(worker, "scan_pr", lambda repo, sha, inst, settings: calls.append((repo, sha, inst)) or ([], []))
    r.lpush(worker.QUEUE, JOB)
    assert worker.process_one(r, settings=None, timeout=1)
    assert calls == [("o/r", SHA, 99)]
    assert lengths(r) == (0, 0, 0)


def test_failing_scan_goes_to_dead_letter(r, monkeypatch):
    def boom(*args):
        raise RuntimeError("git fetch failed")
    monkeypatch.setattr(worker, "scan_pr", boom)
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert lengths(r) == (0, 0, 1)


def test_malformed_job_is_never_scanned(r, monkeypatch):
    monkeypatch.setattr(worker, "scan_pr", lambda *a: pytest.fail("scan_pr must not run"))
    r.lpush(worker.QUEUE, json.dumps({"repo": "o/r"}))
    worker.process_one(r, settings=None, timeout=1)
    assert lengths(r) == (0, 0, 1)


def test_jobs_are_first_in_first_out(r, monkeypatch):
    seen = []
    monkeypatch.setattr(worker, "scan_pr", lambda repo, sha, inst, settings: seen.append(inst) or ([], []))
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
    monkeypatch.setattr(worker, "scan_pr", lambda *a: ([], []))
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert posted == [("o/r", 7)]


def test_failed_scan_posts_nothing(r, monkeypatch, posted):
    def boom(*args):
        raise RuntimeError("semgrep crashed")
    monkeypatch.setattr(worker, "scan_pr", boom)
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert posted == []


def test_partial_scan_still_posts_the_failure(r, monkeypatch):
    failure = ScannerFailure(scanner="semgrep", error="TimeoutExpired")
    sent = []
    monkeypatch.setattr(worker, "scan_pr", lambda *a: ([], [failure]))
    monkeypatch.setattr(worker, "post_report", lambda *args: sent.append(args) or "created")
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert sent[0][6] == [failure]
    assert lengths(r) == (0, 0, 0)
