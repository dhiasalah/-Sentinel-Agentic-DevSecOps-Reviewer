# Week 1 · Step 1.2 — `/health` endpoint + first pytest test

## 🎯 Goal
Add a `GET /health` endpoint and your first automated tests. Docker (step 1.3), Kubernetes and ArgoCD
(week 9) all ask "is this app alive?" by calling a health endpoint, and CI (week 9) runs these tests on every push.

## 💻 Commands
From `apps/api/` with the venv active (`(.venv)` in the prompt):

```powershell
New-Item requirements-dev.txt
New-Item -ItemType Directory tests
New-Item tests/__init__.py, tests/test_main.py
```

Put this in `requirements-dev.txt`:
```
-r requirements.txt
pytest
```
Then install:
```powershell
pip install -r requirements-dev.txt
```
Expected: `Successfully installed ... pytest-8.x ...` (plus a few pytest dependencies).

**Why two files?** `requirements.txt` is what the production container installs. Test tools don't
belong in the image you ship, because every extra package adds size and attack surface. `-r requirements.txt` makes
the dev file include the prod one, so devs install everything with one command.

## 🧩 Code, piece by piece

### 1. The health endpoint
**Where:** `apps/api/app/main.py`, add below the `root()` function.

```python
@app.get("/health")
def health():
    return {"status": "ok"}
```
A deliberately boring endpoint: it returns fast, touches nothing (no DB, no LLM call) and only says
"the process is up and serving HTTP". Orchestrators call it every few seconds, so it must be cheap.

### 2. The test client
**Where:** `apps/api/tests/test_main.py`, at the top.

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
```
`TestClient` calls your app **in-process**: no Uvicorn and no real network. It sends fake HTTP requests
straight into FastAPI, which makes tests fast and means no server has to be running.

### 3. The tests
**Where:** same file, below the client.

```python
def test_root_returns_message():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Sentinel API is running"}


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```
pytest automatically collects any function named `test_*` in files named `test_*.py`. Each test does
one request and checks two things: the **status code** (the contract for machines) and the **body** (the
contract for clients). If either changes by accident, CI goes red.

## 📚 Key concepts
- **Liveness vs readiness** (you'll configure both in week 9):
  *liveness* means "is the process alive?" (if not, Kubernetes restarts it). *Readiness* means "can it
  take traffic right now?", for example when Redis is connected (if not, Kubernetes stops sending requests but doesn't
  kill it). Today's `/health` is a liveness check. [K8s probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- **pytest**: [Getting started](https://docs.pytest.org/en/stable/getting-started.html) ·
  **FastAPI testing**: [docs](https://fastapi.tiangolo.com/tutorial/testing/)

## 🔐 Security note
- Health endpoints are usually **unauthenticated** (the orchestrator has no token), so they must leak
  nothing: no version numbers, env names, stack traces or dependency details. An attacker uses
  `"version": "1.2.3"` to look up known CVEs. `{"status": "ok"}` is all it should say.
- Keeping `pytest` out of the prod image follows **least privilege**, applied to dependencies.

## ✅ Check it works
From `apps/api/`:
```powershell
python -m pytest -v
```
Expected:
```
tests/test_main.py::test_root_returns_message PASSED
tests/test_main.py::test_health_returns_ok PASSED
===== 2 passed in 0.xxs =====
```
You may also see a `StarletteDeprecationWarning` about `httpx`. It's harmless and comes from the libraries, not your code.

Use `python -m pytest`, not plain `pytest`: the `-m` form adds the current folder to Python's import path,
so `from app.main import app` resolves.

Try breaking it: change `"ok"` to `"up"` in `main.py`, rerun, and read how pytest shows the diff. Then revert.

Commit (from repo root):
```powershell
git add apps/api
git commit -m "feat(api): add /health endpoint and first pytest tests"
git push
```

## ➡️ Next step
**1.3: Dockerfile for the API.** Tell Claude **"I finished step 1.2, please review"**.
