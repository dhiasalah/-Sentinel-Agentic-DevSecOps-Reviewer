# Week 3 · Step 3.1 — Create the GitHub App (minimal permissions)

## 🗺️ In plain words: what we're doing today
Right now Sentinel only works when **you** run it by hand on your laptop. The goal is for it to wake up by itself
whenever someone opens a Pull Request on GitHub. To do that, Sentinel needs two things:
1. **Its own identity on GitHub**, a "robot account" called a **GitHub App**, so it doesn't use your personal password.
2. **A doorbell**: every time a PR is opened, GitHub "rings" (sends a message called a **webhook**) to an address we choose.

Today we **create the robot**, allow it into **one test repo only**, open a fake PR, and **watch the doorbell ring**
on a web page (smee.io) and in GitHub's delivery log. Then we write a tiny Python script to prove the robot can
"log in" to GitHub with its secret key. We're not processing anything yet: today is just "the robot exists and
GitHub can reach it".

**Example:** you open a PR in `sentinel-playground` → a few seconds later a new line `pull_request · opened`
appears on smee.io and a ✅ shows up in the app's *Recent Deliveries*. That's the whole goal of Part A.

## 🎯 Goal
Register **Sentinel as a GitHub App**, install it on a throw-away playground repo, and see a real
`pull_request` webhook arrive when you open a PR. Then prove your app's **private key** works by calling
the GitHub API *as the app*. That gives you the identity and the "doorbell" that Sentinel's whole bot runs on.

## 🧰 Tools in this step
- **GitHub App**: a *robot account with a badge*. You say exactly which doors it can open (permissions)
  and on which repos (installation). It is how Sentinel reads PRs and posts comments without your personal password.
  Better than a Personal Access Token (PAT) because a PAT acts as **you** on **all** your repos with no expiry;
  an App gets **only** the permissions you tick, **only** on the repos where it is installed, with **1-hour tokens**.
  Comes back in: 3.2 (webhooks), 3.3 (clone PR), week 4 (post comments), week 6 (open fix PRs), week 7 (dashboard login).
  [Docs](https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/about-creating-github-apps)
- **Webhook**: a *doorbell*. When something happens (a PR is opened), GitHub sends an HTTP POST to a URL you choose.
  Your server does not have to keep asking "anything new?" (polling).
  [Docs](https://docs.github.com/en/webhooks/about-webhooks)
- **smee.io**: a *mail forwarding address*. GitHub can't reach `localhost` on your laptop, so GitHub
  posts to a public smee URL, and (from 3.2) a small client forwards it to your local API. Today we only use its web page to *see* events.
  [smee.io](https://smee.io)
- **JWT (JSON Web Token)** + **PyJWT**: a *signed permission slip*. Your app signs a short note ("I am app 123, valid 10 min")
  with its private key; GitHub checks the signature with the public key it keeps. [PyJWT](https://pyjwt.readthedocs.io/) ·
  [GitHub docs](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app)
- **httpx**: an HTTP client for Python (like `requests`, with timeouts and async). [Docs](https://www.python-httpx.org/)

How they connect (the full picture you'll have by end of week 4):
```
 you open a PR
      │
      ▼
   GitHub ──webhook POST──► smee.io ──forward──► your API (3.2) ──► Redis queue ──► worker (3.4)
                                                                                      │
      ▲                                                                               │
      └──── installation token (1h) ◄── JWT signed with private key (today) ◄─────────┘
            used to read the PR / post the comment
```

## 🔑 Two-level authentication (the key idea of this step)
| Level | Credential | Lifetime | Can do |
|---|---|---|---|
| **App** | JWT signed with the `.pem` private key | ≤ 10 min | only "who am I?", list installations, **ask for an installation token** |
| **Installation** | installation access token | 1 hour | the permissions you ticked, on the repos where the app is installed |

So the `.pem` file is the **master key**: whoever holds it can mint tokens for *every* repo that installed your app.
Installation tokens are the **room keys**: short-lived and limited. Today you use the master key only to prove it works; in 3.3 you exchange it for a room key.

## 💻 Part A — click-ops on github.com

### A1. Playground repo
Create a new repo **`sentinel-playground`** on GitHub (public is fine, it's demo code — add a README so it has a `main` branch).
Copy the vulnerable demo app into it (the Flask app you scanned in 2.1). This is the repo Sentinel will scan. **Never** install the app on repos with real secrets while experimenting.

### A2. smee channel
Open <https://smee.io/new> → you get a URL like `https://smee.io/AbC123xyz`. Keep that tab open (events appear there live).

### A3. Webhook secret
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
Expected output: 64 hex characters, e.g. `3f9a...c21e`. Keep it for A4 and for `.env`.

### A4. Register the app
GitHub → your avatar → **Settings** → **Developer settings** → **GitHub Apps** → **New GitHub App**:

| Field | Value | Why |
|---|---|---|
| GitHub App name | `sentinel-<yourname>` (must be globally unique) | shows on comments ("sentinel-xyz[bot]") |
| Homepage URL | your Sentinel repo URL | required, anything valid |
| Callback URL / "Request user authorization (OAuth)" | leave empty / unchecked | user login is week 7 |
| Webhook → Active | ✅ | we want the doorbell |
| Webhook URL | your smee URL | GitHub can't reach localhost |
| Webhook secret | the value from A3 | lets us **prove** a POST really came from GitHub (3.2) |
| **Repository permissions** → Contents | **Read-only** | clone the PR's code to scan it |
| **Repository permissions** → Pull requests | **Read and write** | read the diff, post the review (week 4) |
| Repository permissions → Metadata | Read-only (forced) | mandatory for every app |
| Everything else | **No access** | least privilege |
| Subscribe to events | ✅ **Pull request** | the only event we need |
| Where can this app be installed? | **Only on this account** | nobody else can install it |

Click **Create GitHub App**. On the next page:
1. Note the **App ID** (a number at the top).
2. Scroll to **Private keys** → **Generate a private key** → a `.pem` file downloads.

### A5. Put the private key OUTSIDE the repo
```powershell
New-Item -ItemType Directory -Force "$HOME\.sentinel" | Out-Null
Move-Item "$HOME\Downloads\sentinel-*.private-key.pem" "$HOME\.sentinel\github-app.pem"
Get-Item "$HOME\.sentinel\github-app.pem" | Select-Object FullName, Length
```
Expected output:
```
FullName                                   Length
--------                                   ------
C:\Users\USER\.sentinel\github-app.pem       1675
```
(Length ~1600–1700 bytes.)

### A6. Install it on the playground only
App settings page → **Install App** → your account → **Only select repositories** → `sentinel-playground` → Install.

### A7. Ring the doorbell
In `sentinel-playground`: create a branch, change one line, open a PR.
- The **smee tab** shows a new event with header `x-github-event: pull_request` and body `"action": "opened"`.
- App settings → **Advanced** → **Recent Deliveries**: a delivery with a ✅ (smee answered 200).

Look at the headers: `x-hub-signature-256: sha256=...` — that's the HMAC you'll verify in 3.2.

## 🧩 Part B — code, piece by piece (in `agents/`)

### 1. Never commit a key file
**Where:** `.gitignore` (repo root) — add under `# Secrets: never commit`
```gitignore
*.pem
```
The key already lives outside the repo; this is belt-and-braces in case someone copies it in later.

### 2. Settings
**Where:** `.env` (root, not committed) — add at the bottom
```
GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=C:\Users\USER\.sentinel\github-app.pem
```
**Where:** `.env.example` — add at the bottom (placeholders only)
```
GITHUB_APP_ID=changeme
GITHUB_PRIVATE_KEY_PATH=C:\path\to\github-app.pem
```
The webhook secret goes into `.env` in 3.2, where the API that checks it lives.

**Where:** `agents/sentinel/config.py` — add `from pathlib import Path` at the top, and these fields at the end of `Settings`
```python
    github_app_id: int | None = None
    github_private_key_path: Path | None = None
```
Optional (`None`) on purpose: the local CLI from 2.4 doesn't need GitHub, so it must keep working without these.
We store a **path**, not the key itself: a multi-line PEM in `.env` is fragile, and in week 9 Kubernetes will mount the key as a file anyway.

### 3. Dependencies
**Where:** `agents/requirements.txt` — add
```
PyJWT[crypto]
httpx
```
```powershell
cd agents; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```
`[crypto]` pulls in `cryptography`, needed for RS256 (RSA signatures). `httpx` is already there indirectly (groq uses it), but anything you `import` yourself must be declared.

### 4. The auth module
**Where:** new files `agents/sentinel/github/__init__.py` (empty) and `agents/sentinel/github/auth.py`
```python
import time
from pathlib import Path

import httpx
import jwt

GITHUB_API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def load_private_key(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def make_app_jwt(app_id: int, private_key_pem: str, now: int | None = None) -> str:
    now = int(time.time()) if now is None else now
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": str(app_id)}
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def get_app_info(app_jwt: str) -> dict:
    resp = httpx.get(
        f"{GITHUB_API}/app",
        headers={**HEADERS, "Authorization": f"Bearer {app_jwt}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
```
- `iat = now - 60`: GitHub's clock and yours may differ by a few seconds; backdating avoids "token used before issued".
- `exp = now + 9 min`: GitHub rejects anything over 10 min. Short life = a stolen JWT is useless quickly.
- `iss`: "issuer" = which app is talking. `now` is a parameter so the test can freeze time.
- `timeout=10`: same rule as the LLM providers — a network call without a timeout can hang a worker forever.

### 5. Test (no network, no real key)
**Where:** new file `agents/tests/test_github_auth.py`
```python
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from sentinel.github.auth import make_app_jwt


def test_app_jwt_is_signed_and_short_lived():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    token = make_app_jwt(42, pem, now=1_000_000)
    claims = jwt.decode(
        token, key.public_key(), algorithms=["RS256"], options={"verify_exp": False}
    )

    assert claims == {"iat": 999_940, "exp": 1_000_540, "iss": "42"}
    assert claims["exp"] - claims["iat"] <= 600
```
The test makes a throw-away RSA key, signs, then verifies with the **public** half — exactly what GitHub does on its side.
`verify_exp=False` because we froze time in 1970.

## 📚 Key concepts
- **Least privilege, as a contract.** Permissions you tick are shown to whoever installs the app, and **adding** a permission later
  makes every installer re-approve. So start minimal and add `Contents: write` only in week 6 (fix PRs), with a reason.
- **Asymmetric keys.** GitHub keeps only the public key → a GitHub breach can't leak your ability to sign. You keep the private key → you must protect it.
- **Push vs pull.** Webhooks (push) = instant and cheap, but your endpoint is public, so you must authenticate the *sender* (3.2).

## 🔐 Security note
- The `.pem` = master key for every installation. Outside the repo, never in `.env` content, never in Docker image layers (week 9: mounted secret).
  If it leaks: App settings → delete the key → generate a new one. Keys don't expire by themselves.
- **smee.io channels are public**: anyone who knows the URL sees the payloads (repo names, PR titles). Fine for a public playground,
  not for private repos. It's a dev tool only; in week 9 GitHub posts straight to your cluster.
- Anyone can POST fake events to your smee URL → that's why the webhook secret + HMAC check in 3.2 is mandatory.
- Worth thinking about: the PR *author* controls the PR's title, body and code. Which of those end up inside the LLM prompt in week 4, and what did 2.3 teach you to do with them?

## ✅ Check it works
1. smee tab shows the `pull_request` / `opened` event; Recent Deliveries shows ✅.
2. Tests:
```powershell
cd agents; python -m pytest -q
```
Expected: `29 passed`.

3. Call GitHub as the app (from `agents/`, venv active):
```powershell
python -c "from sentinel.config import Settings; from sentinel.github.auth import *; s = Settings(); print(get_app_info(make_app_jwt(s.github_app_id, load_private_key(s.github_private_key_path)))['slug'])"
```
Expected output: your app's slug, e.g. `sentinel-yourname`.
A `401 Unauthorized` means wrong App ID or wrong key file.
⚠️ Common trap: leaving the example `GITHUB_APP_ID=123456` in `.env`. GitHub then answers
`"A JSON web token could not be decoded"`: it looks up app 123456's public key, which doesn't match your signature.
Use the real **App ID** (a number, top of the app's *General* page, not the `Iv…` Client ID).

## ➡️ Next step
3.2 — FastAPI `POST /webhooks/github` that verifies `X-Hub-Signature-256` (HMAC) and rejects anything unsigned.
Tell Claude "I finished step 3.1, please review".
