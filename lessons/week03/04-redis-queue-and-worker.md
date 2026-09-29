# Week 3 · Step 3.4 — Redis queue + worker

## 🗺️ In plain words: what we're doing today

Right now two pieces of Sentinel don't talk to each other. The **API** hears "PR #4 was opened" and just logs it.
`scan_pr` (3.3) can scan a PR, but only when you run it by hand. Today we connect them with a **to-do list**:
the API writes a small note ("scan this repo at this commit") into Redis and replies to GitHub right away. A second
program, the **worker**, waits for notes, takes one, runs `scan_pr`, and prints the report.

**Example:** you push a commit to your playground PR. Within a second, the API terminal prints `queued pull_request {...}`.
A few seconds later, the worker terminal prints `scanning dhiasalah/sentinel-playground#4 @ 1a2b3c4`, then the triaged report.
If you click **Redeliver** in GitHub, the API answers `duplicate` and nothing gets scanned twice.

## 🎯 Goal

The week 3 deliverable: **opening or updating a PR triggers a scan, visible in the logs**, with no manual step.
You also get two safety properties that matter for a security bot: **replayed webhooks are ignored** and **no job is silently lost**.

## 🧰 Tools in this step

- **Redis list as a job queue**: Redis (added in 1.4) is an in-memory data store. A *list* is an ordered array you can push to on
  one side and pop from on the other, like a queue at a counter. It solves the timing problem: GitHub waits only **10 s** for a webhook
  reply, and a scan takes 10–60 s. The API pushes and replies `202 Accepted` at once; the worker takes its time.
  Week 5 replaces the worker's body with LangGraph agents, and the queue stays the same.
  [Lists](https://redis.io/docs/latest/develop/data-types/lists/) · [BLMOVE](https://redis.io/docs/latest/commands/blmove/)
- **`SET key value NX EX`**: "set only if it does **N**ot e**X**ist, and **EX**pire after N seconds". It is atomic, so it works as a
  "have I seen this before?" check. We use it to drop replays. [SET](https://redis.io/docs/latest/commands/set/)
- **fakeredis**: an in-memory fake of Redis for tests. Your tests exercise real Redis commands without a running server.
  [fakeredis](https://fakeredis.readthedocs.io/)

```
GitHub ─► smee ─► API /webhooks/github                         Worker (python -m sentinel.worker)
                   1. verify HMAC (3.2)                           loop:
                   2. SET seen:<sha256(body)> NX ── dup? ─► "duplicate"   BLMOVE jobs ─► jobs:processing
                   3. LPUSH sentinel:jobs {job} ───────────────────►     scan_pr(...)   (3.3)
                   4. 202 Accepted (fast)                                 ok   → LREM from processing
                                                                          fail → LPUSH jobs:dead, LREM
```

**Why the API does not import `sentinel` and call `scan_pr` itself.** The API is the one piece that is **reachable from the internet**.
If it ran scans, it would hold the GitHub private key and the LLM keys, and anyone who breaks the API gets all of them. With a queue,
the API only holds the webhook secret. The worker holds the powerful secrets and **accepts no inbound connections at all**.
This is the "API only enqueues, never runs agents" rule from `sentinel-project.md`.

---

## Part A — the API enqueues

### 1. Make Redis reachable from your laptop (dev only)
**Where:** `compose.yaml`, under `redis:` (next to `image:`), add:

```yaml
    ports:
      - "127.0.0.1:6379:6379"
```
Until now, only the `api` container could reach Redis. But you run uvicorn and the worker **on Windows**, not in containers, because
the worker starts Semgrep with `docker run`. `127.0.0.1:` publishes the port **only on your own machine**. Without it, Docker listens on
all interfaces, and anyone on your Wi-Fi could reach a Redis that has **no password**. Default Redis has no auth, and exposed
Redis servers are a classic way servers get compromised.

### 2. Queue the job instead of only logging it
**Where:** `apps/api/app/main.py`

a) Top imports: add `import hashlib` above `import json`.

b) Under `PR_ACTIONS = {...}` add:
```python
QUEUE = "sentinel:jobs"
SEEN_TTL_SECONDS = 24 * 3600
```

c) In `github_webhook`, **replace** the line `logger.info("accepted pull_request %s", job)` with:
```python
    seen_key = "sentinel:seen:" + hashlib.sha256(body).hexdigest()
    try:
        if not redis_client.set(seen_key, 1, nx=True, ex=SEEN_TTL_SECONDS):
            logger.info("duplicate delivery %s ignored", x_github_delivery)
            return {"status": "duplicate"}
        redis_client.lpush(QUEUE, json.dumps(job))
    except redis.RedisError:
        logger.exception("could not enqueue delivery %s", x_github_delivery)
        raise HTTPException(status_code=503, detail="queue unavailable")

    logger.info("queued pull_request %s", job)
```
`SET ... NX` succeeds only the first time a given body is seen. After that, the same body gets `duplicate` for 24 h.
**Why hash the body and not use `X-GitHub-Delivery`?** The HMAC signature covers **the body only, not the headers**. An attacker who
captured one signed webhook (your smee channel is public, remember 3.2) can resend it with any delivery ID they like, and it still
passes the signature check. The body is the part they **cannot** change, so that's what we de-duplicate on.
If Redis is down we return **503**, so the failure shows in GitHub's "Recent deliveries" and you can redeliver later.
Returning 202 here would drop the job without anyone knowing.

### 3. Tests for the queue
**Where:** `apps/api/requirements-dev.txt`, add a line `fakeredis`.

**Where:** `apps/api/tests/test_webhooks.py`

a) Imports: add `import fakeredis` and `import redis` next to `import pytest`.

b) Under the `fixed_secret` fixture add:
```python
@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr(main, "redis_client", fake)
    return fake
```

c) **Replace** the first two lines of `post(...)` so the delivery ID can vary:
```python
def post(body: bytes, signature: str | None, event: str = "pull_request", delivery: str = "d-1"):
    headers = {"X-GitHub-Event": event, "X-GitHub-Delivery": delivery, "Content-Type": "application/json"}
```

d) At the bottom add:
```python
def test_accepted_pull_request_is_queued(fake_redis):
    post(PR_BODY, sign(PR_BODY))
    job = json.loads(fake_redis.rpop(main.QUEUE))
    assert job == {"delivery": "d-1", "repo": "dhiasalah/sentinel-playground", "pr": 7,
                   "head_sha": "abc123", "installation_id": 99}


def test_replayed_body_is_queued_once_even_with_new_delivery_id(fake_redis):
    assert post(PR_BODY, sign(PR_BODY), delivery="d-1").status_code == 202
    replay = post(PR_BODY, sign(PR_BODY), delivery="attacker-made-up-id")
    assert replay.json() == {"status": "duplicate"}
    assert fake_redis.llen(main.QUEUE) == 1


def test_redis_down_returns_503(monkeypatch):
    broken = redis.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    monkeypatch.setattr(main, "redis_client", broken)
    assert post(PR_BODY, sign(PR_BODY)).status_code == 503
```
The autouse fixture gives **every** test a fresh, empty fake Redis. That's why your old "accepted" test still passes: without it, the test would
try a real Redis. The replay test is the important one: it is the attack from the paragraph above, written as a test.

```powershell
cd apps\api; .\.venv\Scripts\Activate.ps1; pip install -r requirements-dev.txt; pytest -q
```
Expected: `13 passed`.

---

## Part B — the worker

### 4. Tell the agents where Redis is
**Where:** `agents/sentinel/config.py`, add under `github_private_key_path`:
```python
    redis_url: str = "redis://localhost:6379/0"
```
**Where:** `agents/requirements.txt` add `redis` · `agents/requirements-dev.txt` add `fakeredis`.

### 5. The worker
**Where:** new file `agents/sentinel/worker.py`, piece 1 of 3 (imports, queue names, job shape):
```python
import logging
import sys

import redis
from pydantic import BaseModel

from sentinel.cli import render_text
from sentinel.config import Settings
from sentinel.github.scan_pr import scan_pr

logger = logging.getLogger(__name__)

QUEUE = "sentinel:jobs"
PROCESSING = "sentinel:jobs:processing"
DEAD = "sentinel:jobs:dead"


class Job(BaseModel):
    delivery: str | None = None
    repo: str
    pr: int
    head_sha: str
    installation_id: int
```
`QUEUE` must match the API's string exactly. It is the **contract** between two programs that never import each other.
`Job` validates each message before using it. Anything that can write to Redis can put a message on the queue, so we check its
shape here, and `checkout.py` still checks `repo` and `head_sha` with its regexes (defense in depth).

Piece 2 (same file, below): one job, safely.
```python
def process_one(r: redis.Redis, settings: Settings, timeout: int = 5) -> bool:
    raw = r.blmove(QUEUE, PROCESSING, timeout, src="RIGHT", dest="LEFT")
    if raw is None:
        return False
    try:
        job = Job.model_validate_json(raw)
        logger.info("scanning %s#%d @ %s (delivery %s)", job.repo, job.pr, job.head_sha[:7], job.delivery)
        issues = scan_pr(job.repo, job.head_sha, job.installation_id, settings)
        report = render_text(issues, sum(len(i.findings) for i in issues))
        logger.info("%s#%d done, %d issue(s)\n%s", job.repo, job.pr, len(issues), report)
    except Exception:
        logger.exception("job failed, moved to %s", DEAD)
        r.lpush(DEAD, raw)
    finally:
        r.lrem(PROCESSING, 1, raw)
    return True
```
This is the **reliable queue** pattern. `BLMOVE` waits up to `timeout` seconds for a job and, **in one atomic step**, moves it from
`jobs` to `jobs:processing`. A plain `RPOP` would make the job exist only in Python memory, so a crash would lose it. The API pushes
on the LEFT and the worker takes from the RIGHT, which gives first-in, first-out order. A failing job goes to a **dead-letter list**
instead of vanishing or retrying forever, so you can inspect it later. The traceback is safe to log because of 3.3: the token lives in an
env var, never in a git command line or URL.

Piece 3 (same file, bottom): start-up and the loop.
```python
def requeue_stale(r: redis.Redis) -> int:
    moved = 0
    while r.lmove(PROCESSING, QUEUE, src="RIGHT", dest="RIGHT") is not None:
        moved += 1
    return moved


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.stderr.reconfigure(encoding="utf-8")
    settings = Settings()
    r = redis.Redis.from_url(settings.redis_url)
    r.ping()
    if moved := requeue_stale(r):
        logger.warning("requeued %d unfinished job(s) from a previous run", moved)
    logger.info("worker ready, waiting for jobs on %s", QUEUE)
    while True:
        process_one(r, settings)


if __name__ == "__main__":
    main()
```
If the worker is killed mid-scan (Ctrl+C, crash, reboot), the job stays in `processing`. On the next start, `requeue_stale` puts it back
at the **front** of the queue. This is only correct with **one** worker: with several, one would steal jobs another is still running.
We'll handle that when we scale workers (week 9). `r.ping()` makes the worker fail fast if Redis is unreachable.
`stderr.reconfigure` is the Windows Unicode fix from 2.2 (logging writes to stderr).

### 6. Worker tests
**Where:** new file `agents/tests/test_worker.py`:
```python
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
```
`scan_pr` is replaced by a fake, so these tests check the **queue logic** (order, cleanup, dead letter, recovery) in about 1 s,
without GitHub, Docker or an LLM. The real pipeline was already proven end to end in 3.3.

```powershell
cd agents; .\.venv\Scripts\Activate.ps1; pip install -r requirements-dev.txt; pytest -q
```
Expected: `40 passed`.

---

## 📚 Key concepts
- **Async work via a queue**: accept fast, work later. It keeps the webhook under GitHub's 10 s limit and absorbs bursts (10 PRs at once
  = 10 queued jobs, not 10 timeouts).
- **At-least-once delivery**: the processing list means a job is never lost, but it *can* run twice (crash after the scan, before `LREM`).
  So jobs should be **idempotent**, meaning safe to run twice. A scan is. Posting a PR comment (week 4) is not, unless we "update the
  existing comment" instead of "add a new one".
- **Dead-letter queue (DLQ)**: where poison messages go, so they don't block the line or vanish.
- **Idempotency key**: `sha256(body)` makes "the same webhook twice" a no-op.
- Why not Celery / RQ / arq? They are this same pattern plus retries, scheduling and dashboards. Writing it by hand once (~40 lines)
  means you'll understand what those libraries do.

## 🔐 Security note
- **Replay protection belongs on signed data.** Headers aren't signed, so we de-duplicate on the body.
- **Privilege separation:** the internet-facing API holds only the webhook secret. The worker holds the private key and LLM keys and
  listens on no port.
- **Redis has no password by default** → published on `127.0.0.1` only. In production (week 8+) it stays on a private network with
  auth (`requirepass`/ACL) and TLS.
- **Denial of wallet:** every `synchronize` event costs an LLM call. The queue makes a spam burst *visible* (`LLEN sentinel:jobs`) but
  doesn't stop it yet. That's a later step.

## ✅ Check it works (live)
```powershell
docker compose up -d redis
docker compose exec redis redis-cli ping
```
Expected: `PONG`. Then open three terminals:

1. API: `cd apps\api; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload`
2. smee: `npx smee-client --url https://smee.io/YOUR_CHANNEL --target http://127.0.0.1:8000/webhooks/github`
3. Worker: `cd agents; .\.venv\Scripts\Activate.ps1; python -m sentinel.worker` → `worker ready, waiting for jobs on sentinel:jobs`

Push any commit to your playground PR branch. Expected: the API prints `queued pull_request {...}`, the worker prints
`scanning dhiasalah/sentinel-playground#4 @ …`, then the report and `removed C:\…\Temp\sentinel-…`.

Then try the two safety features:
- GitHub → your App → **Advanced** → Recent deliveries → **Redeliver** the same event → API logs `duplicate delivery … ignored`.
- Push again, press **Ctrl+C** in the worker while it's scanning, then restart it → `requeued 1 unfinished job(s)` and the scan runs.

Peek inside Redis at any time:
```powershell
docker compose exec redis redis-cli LLEN sentinel:jobs
docker compose exec redis redis-cli LRANGE sentinel:jobs:dead 0 -1
```

**Worth thinking about:** a job that *crashes the whole process* (not an exception, say Semgrep eats all the RAM and the OS kills the
worker) gets requeued on every restart and kills it again: a poison-pill loop. How would you break that loop? (Hint: count attempts.)

## ➡️ Next step
Week 4: the worker posts the report as a PR comment. Tell Claude "I finished step 3.4, please review".
