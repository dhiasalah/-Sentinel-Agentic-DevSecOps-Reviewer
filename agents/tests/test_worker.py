import json

import fakeredis
import pytest

from sentinel import worker

SHA = "a" * 40
JOB = json.dumps({"delivery": "d-1", "repo": "o/r", "pr": 7, "head_sha": SHA, "installation_id": 99})


@pytest.fixture
def r():
    return fakeredis.FakeRedis()


def lengths(r):
    return r.llen(worker.QUEUE), r.llen(worker.PROCESSING), r.llen(worker.DEAD)


def test_job_is_scanned_then_removed(r, monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "scan_pr", lambda repo, sha, inst, settings: calls.append((repo, sha, inst)) or [])
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
    monkeypatch.setattr(worker, "scan_pr", lambda repo, sha, inst, settings: seen.append(inst) or [])
    for inst in (1, 2, 3):
        r.lpush(worker.QUEUE, JOB.replace("99", str(inst)))
    while worker.process_one(r, settings=None, timeout=1):
        pass
    assert seen == [1, 2, 3]


def test_unfinished_jobs_are_requeued_on_start(r):
    r.lpush(worker.PROCESSING, JOB)
    assert worker.requeue_stale(r) == 1
    assert lengths(r) == (1, 0, 0)
