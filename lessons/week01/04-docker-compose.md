# Week 1 · Step 1.4 — Docker Compose (API + Redis)

## 🎯 Goal

Run the API **and** Redis together with one command: `docker compose up`. Redis will become Sentinel's
**job queue** in week 3 (webhook arrives → job goes into Redis → a worker scans the PR). Today you also
connect the API to Redis with a `/ready` endpoint, so you can _see_ liveness vs readiness working.

## 🧰 Tools in this step

### Docker (quick recap)

- **What it is:** a way to put your app **plus everything it needs** (Python, libraries, settings) into one
  sealed box called a **container**. Analogy: a shipping container. Whatever is inside, every ship and
  crane handles it the same way.
- **Problem it solves:** "it works on my machine". The box runs the same on your Windows laptop, in
  GitHub Actions and on the Linux server.
- **Words:** the **Dockerfile** is the recipe, the **image** is the result of cooking the recipe (frozen,
  shareable), and a **container** is a running copy of an image.
- **In Sentinel:** every piece (API, worker, scanners, sandbox) will be a container. In week 9 Kubernetes runs them on the server. [Docs](https://docs.docker.com/get-started/docker-overview/)

### Docker Compose

- **What it is:** a tool that starts **several containers together** from one file (`compose.yaml`).
  Analogy: if Docker runs one musician, Compose is the conductor with the sheet music for the whole band.
- **Problem it solves:** without it you'd type long `docker run ...` commands for each container, create
  a network by hand, and start them in the right order. Compose does all that with `docker compose up`.
- **What it gives you for free:** a **private network** where containers find each other **by name**
  (the API reaches Redis at the hostname `redis`), start order, restart on crash, and volumes.
- **In Sentinel:** your local dev setup (API + Redis now; worker and scanners later). In week 9 Kubernetes
  takes over the same job on the server, with the same ideas. [Docs](https://docs.docker.com/compose/)

### Redis

- **What it is:** a database that keeps data **in memory** (RAM), so it's extremely fast. It stores
  simple things: keys → values, lists, queues. Analogy: a whiteboard in the office, fast to write on and
  read from, not a filing cabinet for long-term records (that's Postgres, week 7).
- **Problem it solves for us:** a **job queue**. A GitHub webhook must be answered in a few seconds, but
  a security scan takes minutes. So the API writes "scan PR #42" on the whiteboard (Redis) and answers
  GitHub immediately, and a separate **worker** picks up jobs from the board and does the slow work.
- **In Sentinel:** today you only check it's reachable (`ping`). Week 3 adds the real queue + worker. [Docs](https://redis.io/docs/latest/get-started/)

### redis-py (the `redis` Python package)

- **What it is:** the Python library your API uses to **talk to** Redis. Redis is the server (the
  whiteboard), and redis-py is the marker your code holds. [Docs](https://redis.readthedocs.io/en/stable/)

### Environment variables

- **What they are:** settings given to a program **from outside**, when it starts (like `REDIS_URL=...`).
  Analogy: the same car (image) driven by different drivers with different GPS destinations.
- **Why:** the same image must run on your laptop, in CI and in prod, and only the addresses and passwords
  change. Hardcoding them means rebuilding per environment and risks committing secrets. Step 1.5
  uses this for API keys.

### pytest `monkeypatch`

- **What it is:** a pytest helper that **temporarily swaps** a piece of your code for a fake during one
  test, then puts the real one back. Analogy: a stunt double for a dangerous scene.
- **Why:** to test "what happens when Redis is down?" without actually breaking Redis. [Docs](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)

### How it all connects

```
 your browser / curl.exe
          │  http://127.0.0.1:8000
          ▼
 ┌──────────────── Docker (started by: docker compose up) ────────────────┐
 │                                                                        │
 │   ┌───────────────┐     private network      ┌───────────────┐         │
 │   │  api          │ ───── redis:6379 ──────▶ │  redis        │         │
 │   │  (FastAPI +   │     "PING" → "PONG"      │  (in-memory   │         │
 │   │   uvicorn)    │                          │   store)      │         │
 │   └───────────────┘                          └──────┬────────┘         │
 │     port 8000 published                             │ no port          │
 │     to your machine only                            │ published        │
 │                                              volume: redis-data        │
 └────────────────────────────────────────────────────────────────────────┘
```

Only the API has a door to the outside. Redis is reachable **only** by the API through the private network.

## 💻 Commands

Add the Redis client library. **Where:** `apps/api/requirements.txt` becomes:

```
fastapi[standard]
redis
```

Install it locally (from `apps/api/`, venv active) so your tests can import it:

```powershell
pip install -r requirements-dev.txt
```

Expected: `Successfully installed redis-...`.

Create the compose file at the **repo root**:

```powershell
New-Item compose.yaml
```

## 🧩 Code, piece by piece

### 1. Connect the API to Redis

**Where:** `apps/api/app/main.py`, replace the import line at the top.

```python
import os

import redis
from fastapi import FastAPI, HTTPException

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=2)
```

The Redis address comes from an **environment variable**, not from the code. Locally it defaults to
`localhost`; in Compose it will be `redis://redis:6379/0`, and in Kubernetes something else, all with the
same image. `from_url` doesn't connect yet (it's lazy); it connects on the first command.
`socket_connect_timeout=2` means that if Redis is down, you fail in 2s instead of hanging.

### 2. The readiness endpoint

**Where:** same file, below `health()`.

```python
@app.get("/ready")
def ready():
    try:
        redis_client.ping()
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="redis unavailable")
    return {"status": "ready"}
```

`/health` answers "is the process alive?". `/ready` answers "can I actually do my job?", which for
Sentinel means "can I reach the queue?". `503 Service Unavailable` is the standard code that tells a load
balancer or Kubernetes "don't send me traffic right now, but don't kill me either". The error message
stays generic: it doesn't include the Redis URL or the exception text.

### 3. Test the failure path (mocking)

**Where:** `apps/api/tests/test_main.py`. Add the imports at the top and the test at the bottom.

```python
import redis

from app import main
```

```python
def test_ready_returns_503_when_redis_is_down(monkeypatch):
    def fake_ping():
        raise redis.ConnectionError("down")

    monkeypatch.setattr(main.redis_client, "ping", fake_ping)

    response = client.get("/ready")
    assert response.status_code == 503
```

Unit tests shouldn't need a real Redis. `monkeypatch` temporarily replaces `redis_client.ping` with a
fake that fails, then restores it after the test. This lets you test the **error path**, the one that
matters at 3 a.m. and that you'd never trigger by hand.

### 4. Compose: the API service

**Where:** `compose.yaml` (repo root), at the top.

```yaml
name: sentinel

services:
  api:
    build: ./apps/api
    image: sentinel-api:dev
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
```

- `build` points at the folder with your Dockerfile, and `image` names the result.
- `REDIS_URL` uses the hostname **`redis`**: Compose puts all services on a private network where each
  service name works as a DNS name.
- `127.0.0.1:8000:8000` publishes the port **only on your machine**. With plain `"8000:8000"`, Docker
  listens on all interfaces, so anyone on your Wi-Fi could reach it (and on Linux servers Docker even bypasses the firewall).
- `depends_on ... service_healthy` waits until Redis passes its healthcheck before starting the API.
- `restart: unless-stopped` restarts the container automatically if it crashes.

### 5. Compose: the Redis service

**Where:** same file, below the `api` service (same indentation as `api:`), then the `volumes` block at the very end (no indentation).

```yaml
  redis:
    image: redis:8-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  redis-data:
```

- Redis has **no `ports:`**, on purpose. Only the API can reach it through the private network; your
  laptop and the internet can't. Redis has no password by default, and exposed Redis servers are one of
  the most common ways servers get hijacked (bots find them and install crypto-miners).
- `redis-cli ping` → `PONG` is how Compose knows Redis is healthy.
- The **named volume** `redis-data` keeps Redis data when the container is recreated. Without it, the
  queue would be wiped every time.

## 📚 Key concepts

- **Compose** describes a multi-container app in one file: services, network, volumes. It's your local
  stand-in for what Kubernetes does in week 9 (same ideas: services, env vars, health, volumes).
- **Config via environment variables** (the "12-factor" rule): the same image goes to dev, CI and prod, and only the env changes. [12factor.net/config](https://12factor.net/config)
- Docs: [Compose file reference](https://docs.docker.com/reference/compose-file/) ·
  [redis-py](https://redis.readthedocs.io/en/stable/) · [pytest monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)

## 🔐 Security note

- Internal services (Redis, later Postgres) are **never published**. Only the entry point (the API) is.
- Publish on `127.0.0.1` in dev. In production the only public door will be the ingress/load balancer.
- Redis still has no password here. That's acceptable only because it's unreachable from outside, and
  you'll add auth when secrets arrive (step 1.5 / week 9).

## ✅ Check it works

Tests first (from `apps/api/`):

```powershell
python -m pytest -v
```

Expected: `3 passed`.

Start everything (from the **repo root**):

```powershell
docker compose up --build -d
docker compose ps
```

Expected (after ~10s):

```
NAME               IMAGE              ...   STATUS                   PORTS
sentinel-api-1     sentinel-api:dev   ...   Up 10 seconds (healthy)  127.0.0.1:8000->8000/tcp
sentinel-redis-1   redis:8-alpine     ...   Up 16 seconds (healthy)  6379/tcp
```

Note that Redis shows `6379/tcp` with **no** `127.0.0.1:` or `0.0.0.0:` mapping, so it isn't reachable from your machine.

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/ready
```

Expected: `{"status":"ok"}` and `{"status":"ready"}`.

**See liveness vs readiness live.** Kill Redis:

```powershell
docker compose stop redis
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/ready
```

Expected: `/health` → `{"status":"ok"}` (process alive), `/ready` → `{"detail":"redis unavailable"}`
(503: can't do its job). Then bring Redis back with `docker compose start redis`, and `/ready` recovers on its own.

Logs and cleanup:

```powershell
docker compose logs api
docker compose down
```

`down` removes the containers and network but **keeps** the `redis-data` volume (`down -v` would delete it too).

Commit (from repo root):

```powershell
git add compose.yaml apps/api
git commit -m "feat: add docker compose with API and Redis, /ready endpoint"
git push
```

## ➡️ Next step

**1.5: API keys (Gemini, Groq) + `.env` handling.** Tell Claude **"I finished step 1.4, please review"**.
