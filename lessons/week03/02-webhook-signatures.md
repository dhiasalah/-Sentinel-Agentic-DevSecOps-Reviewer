# Week 3 · Step 3.2 — Verify webhook signatures (`POST /webhooks/github`)

## 🗺️ In plain words: what we're doing today
In 3.1 the doorbell rang, but it rang on a web page (smee.io) and nobody answered. Today your **API answers the door**.
We add a route `POST /webhooks/github` and run a small forwarder on your laptop that passes smee's messages to it.
The important part is the **peephole**. The URL is public, so anyone can send your API a fake message like
"PR opened, go scan this". Before trusting a message, the API checks a **seal** that only GitHub can make, because only
GitHub and you know the webhook secret. If there's no seal or the seal is wrong, the answer is `401` and nothing happens.

**Example:** you click *Redeliver* on your PR event in GitHub. Your uvicorn terminal prints
`accepted pull_request {'repo': 'dhiasalah/sentinel-playground', 'pr': 1, ...}` and `202 Accepted`. A fake POST
you send yourself without the seal gets `401`.

## 🎯 Goal
A FastAPI webhook endpoint that **authenticates the sender** (HMAC SHA-256 over the raw body, constant-time compare),
ignores events we don't care about, and logs the few facts the worker will need in 3.3 (repo, PR number, head SHA, installation id).

## 🧰 Tools in this step
- **HMAC SHA-256**: a *wax seal made with a shared stamp*. GitHub computes `HMAC(secret, body)` and sends it in the
  `X-Hub-Signature-256` header. You compute the same thing with your copy of the secret. If the two match, the body came from
  someone who knows the secret and wasn't changed on the way. It's in Python's standard library (`hmac`, `hashlib`), so there's nothing to install.
  [GitHub docs](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries) · [hmac](https://docs.python.org/3/library/hmac.html)
- **smee-client** (`npx smee-client`): the *mail forwarder*. It keeps a connection open to your smee channel and re-POSTs every
  event to `http://127.0.0.1:8000/...`. It needs Node (you have v22). You only use it in dev; from week 9 GitHub posts straight to the cluster.
  [smee.io](https://smee.io) · [smee-client](https://github.com/probot/smee-client)
- **FastAPI `Request` + `Header`**: read the **raw bytes** of the body, plus specific headers. [Docs](https://fastapi.tiangolo.com/advanced/using-request-directly/)

```
GitHub ──POST + X-Hub-Signature-256──► smee.io ──► smee-client (your laptop) ──► uvicorn :8000 /webhooks/github
                                                                                   │
                                                          verify HMAC(secret, raw body)
                                                              │ bad → 401, stop
                                                              ▼ good
                                                 pull_request opened/synchronize/reopened?
                                                     no → 200 "ignored"   yes → log job, 202
                                                                                   (3.4: push job to Redis)
```

## 🔑 Two kinds of signatures (3.1 vs 3.2)
| | 3.1 App JWT | 3.2 Webhook HMAC |
|---|---|---|
| Who signs | **you** (Sentinel → GitHub) | **GitHub** (GitHub → Sentinel) |
| Key type | asymmetric (private `.pem` / public key) | **symmetric** (same secret on both sides) |
| Proves | "this request comes from app `sentinel-dhia`" | "this event comes from GitHub and wasn't modified" |
| If the key leaks | attacker acts **as your app** on every installation | attacker can **send fake events** to your API |

## 🧩 Code, piece by piece (in `apps/api/`)

### 1. The secret
**Where:** root `.env` (not committed). Add the 64-hex value you generated in 3.1 step A3:
```
GITHUB_WEBHOOK_SECRET=<the value from 3.1 A3>
```
Lost it? Generate a new one (`python -c "import secrets; print(secrets.token_hex(32))"`), then paste it in **both** `.env` and
GitHub → your app → *General* → *Webhook secret* → *Save changes*.

**Where:** `.env.example`, add at the bottom:
```
GITHUB_WEBHOOK_SECRET=changeme
```

**Where:** `apps/api/app/config.py`, add as the last field of `Settings`:
```python
    github_webhook_secret: SecretStr
```
It's required (no default), just like the LLM keys. An API that can't verify webhooks shouldn't start at all (fail fast).
`SecretStr` keeps it out of logs and tracebacks.

### 2. The verifier
**Where:** new file `apps/api/app/webhooks.py`
```python
import hashlib
import hmac


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
```
- `if not secret`: an empty secret is a key anyone can use (`HMAC("", body)` is public knowledge). So we **fail closed**.
- `compare_digest`: a normal `==` stops at the first different character. By measuring response times over many tries, an attacker
  could guess a valid signature one character at a time (a **timing attack**). `compare_digest` always takes the same time.
- It's a pure function (no FastAPI, no settings), so it's trivial to test and reuse.

### 3. The route
**Where:** `apps/api/app/main.py`. **Replace** the import block at the top with:
```python
import json
import logging
from typing import Annotated

import redis
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.webhooks import verify_signature

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel.webhooks")
PR_ACTIONS = {"opened", "synchronize", "reopened"}
```
**Where:** same file, add at the bottom:
```python
@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
    x_github_delivery: Annotated[str | None, Header()] = None,
):
    body = await request.body()
    if not verify_signature(settings.github_webhook_secret.get_secret_value(), body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="invalid signature")

    if x_github_event == "ping":
        return {"status": "pong"}

    payload = json.loads(body)
    if x_github_event != "pull_request" or payload.get("action") not in PR_ACTIONS:
        return {"status": "ignored"}

    pr = payload["pull_request"]
    job = {
        "delivery": x_github_delivery,
        "repo": payload["repository"]["full_name"],
        "pr": pr["number"],
        "head_sha": pr["head"]["sha"],
        "installation_id": payload["installation"]["id"],
    }
    logger.info("accepted pull_request %s", job)
    return JSONResponse(status_code=202, content={"status": "accepted", "pr": job["pr"]})
```
- **Raw bytes, not a Pydantic model.** GitHub signed the *exact bytes* it sent. If FastAPI parsed the JSON first, re-serializing
  it could change spacing or key order and break the HMAC. Also, parsing is attack surface: **never parse untrusted input
  before you've authenticated it.** That's why `json.loads` comes *after* the check.
- FastAPI maps `x_hub_signature_256` → header `X-Hub-Signature-256` (underscores become dashes, case doesn't matter).
- `ping` is sent once when a webhook is created. Answering it keeps GitHub's delivery log green.
- `opened` / `synchronize` (new commits pushed) / `reopened` are the only actions that change the code to scan.
  Title edits, labels and closing are ignored.
- `202 Accepted` means "got it, I'll work on it later". GitHub waits **at most 10 seconds** for an answer, and a scan takes longer. So the
  handler must only *enqueue* the work (3.4) and never do it inline.
- The `job` dict is exactly what the worker needs in 3.3: `installation_id` → installation token, `repo` + `head_sha` → clone.
- `detail="invalid signature"` is deliberately vague: don't tell an attacker *which* part was wrong.

### 4. Tests
**Where:** new file `apps/api/tests/test_webhooks.py`
```python
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import main

SECRET = "test-secret"
client = TestClient(main.app)

PR_BODY = json.dumps({
    "action": "opened",
    "pull_request": {"number": 7, "head": {"sha": "abc123"}},
    "repository": {"full_name": "dhiasalah/sentinel-playground"},
    "installation": {"id": 99},
}).encode()


@pytest.fixture(autouse=True)
def fixed_secret(monkeypatch):
    monkeypatch.setattr(main.settings, "github_webhook_secret", SecretStr(SECRET))


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post(body: bytes, signature: str | None, event: str = "pull_request"):
    headers = {"X-GitHub-Event": event, "X-GitHub-Delivery": "d-1", "Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return client.post("/webhooks/github", content=body, headers=headers)


def test_signed_pull_request_is_accepted():
    response = post(PR_BODY, sign(PR_BODY))
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "pr": 7}


def test_missing_signature_is_rejected():
    assert post(PR_BODY, None).status_code == 401


def test_wrong_secret_is_rejected():
    assert post(PR_BODY, sign(PR_BODY, "attacker-guess")).status_code == 401


def test_tampered_body_is_rejected():
    tampered = PR_BODY.replace(b'"number": 7', b'"number": 8')
    assert post(tampered, sign(PR_BODY)).status_code == 401


def test_irrelevant_action_is_ignored():
    body = json.dumps({"action": "closed"}).encode()
    response = post(body, sign(body))
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_empty_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(main.settings, "github_webhook_secret", SecretStr(""))
    assert post(PR_BODY, sign(PR_BODY, "")).status_code == 401
```
The fixture pins a known secret so the tests never depend on your real `.env` value. Each attack gets its own test:
no seal, forged seal, seal reused on a modified body, empty secret. The last one is the guardrail from piece 2. Without it,
a missing secret would silently accept *everything*.

## ✅ Check it works
1. Tests (from `apps/api/`, venv active):
```powershell
cd apps\api; .\.venv\Scripts\Activate.ps1; python -m pytest -q
```
Expected: `10 passed` (4 old + 6 new).

2. **Terminal 1**, start the API:
```powershell
cd apps\api; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload
```
Expected: `Uvicorn running on http://127.0.0.1:8000`.

3. **Terminal 2**, start the forwarder (use *your* smee URL). The first time, npx asks `Ok to proceed? (y)`: answer `y`.
```powershell
npx smee-client --url https://smee.io/YOUR_CHANNEL --target http://127.0.0.1:8000/webhooks/github
```
Expected: `Forwarding https://smee.io/YOUR_CHANNEL to http://127.0.0.1:8000/webhooks/github` then `Connected`.

4. **Real event:** GitHub → your app → *Advanced* → *Recent Deliveries* → open the `pull_request.opened` from 3.1 → **Redeliver**.
   (Or push a new commit to the PR branch, which sends a `synchronize` event.) Terminal 1 should show:
```
INFO:sentinel.webhooks:accepted pull_request {'delivery': '…', 'repo': 'dhiasalah/sentinel-playground', 'pr': 1, 'head_sha': '…', 'installation_id': …}
INFO:     127.0.0.1:…… - "POST /webhooks/github HTTP/1.1" 202 Accepted
```

5. **Fake event** (a third terminal, no signature):
```powershell
try { Invoke-WebRequest -Method Post -Uri http://127.0.0.1:8000/webhooks/github -Body '{"action":"opened"}' -ContentType application/json -Headers @{"X-GitHub-Event"="pull_request"} -UseBasicParsing } catch { $_.Exception.Response.StatusCode.value__ }
```
Expected output: `401`.

If step 4 gives `401`: either the secret in `.env` ≠ the one in the app settings, or uvicorn started before you edited `.env`
(restart it). If it's still 401 after that, tell Claude. smee re-sends the JSON, and in rare cases that changes the bytes.

## 📚 Key concepts
- **Authenticate the sender, not the network.** The endpoint is public by design. Security comes from the seal, not from hiding the URL.
- **Verify, then parse.** Unauthenticated input gets the minimum possible processing.
- **Acknowledge fast, work later.** Webhook handlers have deadlines (GitHub: 10 s). Long work goes to a queue (3.4).
- **Symmetric vs asymmetric.** HMAC is fast and simple but both sides hold the same key. JWT/RSA keeps the signing key in one place only.

## 🔐 Security note
- **Replay attacks.** The HMAC proves "GitHub sent this once", but it has **no timestamp**. Your smee channel is **public**, so anyone
  watching it can copy a signed delivery and POST it again: the seal is still valid. Result: duplicate scans (wasted LLM quota = a
  cheap denial-of-wallet attack). Fix in 3.4: remember each `X-GitHub-Delivery` id in Redis (`SET key NX EX 86400`) and drop repeats.
- **Log safely.** We log only repo name, numbers and SHA. We never log the PR title or body: the PR author controls them, and they could
  contain fake log lines (log injection) or, later, prompt injection.
- **Rotate if leaked.** A leaked webhook secret = anyone can trigger scans. Generate a new one and update both sides.
- **Body size.** GitHub caps payloads at 25 MB. In week 9 the ingress will enforce a smaller limit before the request reaches Python.
- Worth thinking about: `synchronize` lets the PR author trigger a new scan with every push. What would stop someone from pushing 500 commits
  to burn your Gemini/Groq quota? (Hint: rate limiting per repo/PR, week 4–8.)

## ➡️ Next step
3.3: use `installation_id` to get a 1-hour installation token and clone the PR's `head_sha` into a temp folder.
Tell Claude "I finished step 3.2, please review".
