# Week 1 · Step 1.5 — API keys (Gemini, Groq) + `.env` / secrets handling

## 🎯 Goal

Get the two LLM API keys Sentinel's agents will use from week 2, and store them **safely**: in a `.env`
file that never reaches git, loaded into a typed, validated config object whose secrets never show up in
logs. Your repo is **public**, so this step is the difference between "fine" and "someone runs up a bill on your account".

## 🧰 Tools in this step

### LLM APIs: Gemini and Groq

- **What they are:** websites that host AI models. You send text over HTTP, and the model's answer comes
  back. Analogy: a very smart colleague you reach by phone. The **API key** is your phone number _and_
  your credit card: whoever has it can call as you, and it's billed to you.
- **Gemini** (Google): a strong model with a generous free tier → Sentinel's **primary** brain for triage and fixes.
- **Groq**: runs open models (Llama etc.) on very fast chips. It's also free, so it's the **fallback** when Gemini
  is down or rate-limited. You'll build this "router" in week 2.
- Docs: [Gemini API](https://ai.google.dev/gemini-api/docs/api-key) · [Groq](https://console.groq.com/docs/quickstart)

### `.env` file

- **What it is:** a plain text file of `NAME=value` lines holding your environment variables for local
  dev. Analogy: a sticky note with passwords, kept in your drawer, **never** in the shared folder (git).
- **`.env.example`**: the same file with **fake** values, committed to git. It tells others (and future
  you) _which_ variables exist without revealing them.

### pydantic-settings

- **What it is:** a library that reads environment variables (and `.env`) into a **Python class with
  types**. Analogy: a customs officer who checks every setting at startup ("is it there? is it the right
  type?") instead of letting a missing key crash the app 20 minutes later mid-scan.
- **`SecretStr`**: a type that **hides** the value when printed: `SecretStr('**********')`. So if you log
  the settings by accident, the keys don't end up in log files, Langfuse traces (week 10) or error pages.
- Docs: [Settings management](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) · [SecretStr](https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr)

### How it connects

```
  .env  (your laptop only, git-ignored)
    │
    ├─▶ python -m pytest / uvicorn ──▶ Settings() reads .env directly
    │
    └─▶ docker compose up ──▶ env_file: .env ──▶ container env vars ──▶ Settings() reads env vars
                                                                          │
                                                          settings.gemini_api_key (SecretStr)
```

## 💻 Commands

### 1. Get the keys (in the browser)

- Gemini: https://aistudio.google.com/apikey → **Create API key**.
- Groq: https://console.groq.com/keys → **Create API Key** (it's shown **only once**, so copy it right away).

Don't paste keys into chat, screenshots, issues or commits, and that includes this conversation with Claude.

### 2. Install pydantic-settings

**Where:** `apps/api/requirements.txt` becomes:

```
fastapi[standard]
redis
pydantic-settings
```

From `apps/api/`, venv active:

```powershell
pip install -r requirements-dev.txt
```

Expected: `Successfully installed pydantic-settings-... python-dotenv-...`.

### 3. Fix `.gitignore` first (still pending from step 1.1)

**Where:** root `.gitignore`, line 2: replace `apps/api/.venv/` with:

```gitignore
.venv/
```

From now on, fix the ignore rules _before_ creating any secret file.

## 🧩 Code, piece by piece

### 1. `.env.example` (committed)

**Where:** repo root, new file `.env.example`.

```dotenv
# Copy to .env and fill in real values. Never commit .env.
GEMINI_API_KEY=changeme
GROQ_API_KEY=changeme
REDIS_URL=redis://localhost:6379/0
```

This is the documentation of your config. Your `.gitignore` already has `!.env.example`, which
re-allows this one file even though `.env.*` is ignored.

### 2. `.env` (never committed)

From the repo root:

```powershell
Copy-Item .env.example .env
git check-ignore -v .env
```

Expected: `.gitignore:7:.env	.env`. Git confirms which rule ignores it. **If this prints nothing,
stop**: the file is _not_ ignored. Now open `.env` and replace the two `changeme` values with your real keys.

### 3. The settings class

**Where:** new file `apps/api/app/config.py`, at the top.

```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    gemini_api_key: SecretStr
    groq_api_key: SecretStr
```

Each field maps to an env var with the same name, case-insensitive (`gemini_api_key` ← `GEMINI_API_KEY`).
The fields **without a default are required**: if a key is missing, the app refuses to start with a clear
error (fail fast). `env_file` lists two paths so it finds the root `.env` whether you run from the repo
root or from `apps/api`. Missing files are simply skipped, and in the container there's no file at all,
because the values arrive as real env vars. `extra="ignore"` means other variables in `.env` (for future
services) don't cause errors. Real env vars **win over** `.env`, which is how Compose can override `REDIS_URL`.

### 4. One shared instance

**Where:** same file, at the bottom.

```python
settings = Settings()
```

It's created once at import time, and every module does `from app.config import settings`. One place reads
config, and everything else uses it.

### 5. Use it in the API

**Where:** `apps/api/app/main.py`. Delete `import os` and the `REDIS_URL = os.getenv(...)` line, add
the import next to the others, and change the `redis_client` line:

```python
from app.config import settings
```

```python
redis_client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
```

The API no longer reads env vars itself: it asks the validated settings object.

### 6. Pass the keys to the container

**Where:** `compose.yaml`, in the `api` service, on its own line **above** `environment:`, at the
**same indentation** as `environment:` (4 spaces), not inside it:

```yaml
env_file: .env
environment:
  REDIS_URL: redis://redis:6379/0
```

> ⚠️ **Indentation is meaning in YAML.** If you indent `env_file: .env` under `environment:` (6 spaces),
> Compose doesn't complain: it creates an env var literally _named_ `env_file` with the value `.env`, and
> your keys never reach the container. The app then crashes at startup with
> `2 validation errors for Settings … gemini_api_key Field required` (the fail-fast check doing its job).
> Compose loads every line of `.env` into the container's environment. The `environment:` block
> (`REDIS_URL: redis://redis:6379/0`) has **higher priority** than `env_file`, so inside Docker the API
> still uses the hostname `redis`, while your laptop uses `localhost` from `.env`. The keys enter at
> **runtime** and are never baked into the image (lesson 03's rule).

### 7. A test that secrets can't leak

**Where:** `apps/api/tests/test_main.py`. Add the import at the top and the test at the bottom.

```python
from app.config import settings
```

```python
def test_secrets_are_hidden_when_printed():
    real_key = settings.gemini_api_key.get_secret_value()
    assert real_key not in str(settings)
    assert real_key not in repr(settings)
```

`get_secret_value()` is the **only** way to read the real key, so later, when you search the code for
`get_secret_value`, you find every place a secret is actually used. The test guards against someone
(future you) changing the type to plain `str`.

**Clean-up while you're here:** your test file imports the app twice (`from app.main import app` and
`from app import main`). Keep only `from app import main` and use `TestClient(main.app)`. Also group the
imports: third-party ones first (`redis`, `fastapi`), a blank line, then yours (`app...`).

## 📚 Key concepts

- **Secret lifecycle**: where secrets live in each environment: local = `.env` (git-ignored), CI =
  GitHub Actions secrets (week 9), cluster = Sealed Secrets (week 9). The code is the same everywhere
  (`Settings()`), and only the _source_ changes.
- **Fail fast**: validate config at startup, not at first use.

## 🔐 Security note

- **If a key ever lands in a commit, deleting it is NOT enough.** It stays in git history, and bots scrape
  public GitHub for keys within minutes. The only fix is to **revoke the key** in the provider console and create a new one.
- `env_file` values are visible to anyone who can run `docker inspect` on your machine. That's fine for local dev.
  Production gets proper secret management in week 9.
- Keys give access to _your_ quota and billing. Use separate keys per environment (dev / prod), so you can revoke one without breaking the other.
- Never log `get_secret_value()` output, and never put keys in URLs (`?key=...`), because URLs end up in logs and proxy history.

## ✅ Check it works

Tests (from `apps/api/`):

```powershell
python -m pytest -v
```

Expected: `4 passed`.

Fail-fast check: temporarily rename `.env` and run the tests again:

```powershell
Rename-Item ..\..\.env .env.bak
python -m pytest -q
Rename-Item ..\..\.env.bak .env
```

Expected (middle command): a collection error containing
`ValidationError: 2 validation errors for Settings` … `gemini_api_key  Field required`. That's the app refusing to run without keys.

Containers (from repo root):

```powershell
docker compose up --build -d
curl.exe http://127.0.0.1:8000/ready
docker compose exec api python -c "from app.config import settings; print(settings)"
```

Expected:

```
{"status":"ready"}
redis_url='redis://redis:6379/0' gemini_api_key=SecretStr('**********') groq_api_key=SecretStr('**********')
```

`redis_url` shows `redis` (not `localhost`), which proves `environment:` overrides `.env`, and the keys are masked.

**Before committing**, make sure `.env` isn't staged:

```powershell
git status
```

Expected: you see `.env.example`, `.gitignore`, `compose.yaml` and `apps/api/...`, but **no `.env`**.

```powershell
git add .gitignore .env.example compose.yaml apps/api
git commit -m "feat(api): typed settings with SecretStr, .env handling for LLM keys"
git push
docker compose down
```

## ➡️ Next step

**1.6: Sign up for Oracle Cloud** (the free server you'll deploy to in week 9). Tell Claude **"I finished step 1.5, please review"**.
