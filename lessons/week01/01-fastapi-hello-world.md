# Week 1 · Step 1.1 — Python venv + first FastAPI "hello world"

## 🎯 Goal
A running FastAPI server in `apps/api` that answers `GET /` with JSON. This is the start of Sentinel's
**API gateway**, which will later receive GitHub webhooks.

## 💻 Commands
From the repo root, in PowerShell:

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install "fastapi[standard]"
```
Expected: your prompt starts with `(.venv)` and pip ends with `Successfully installed fastapi-... uvicorn-... ...`.

> If activation fails with *"running scripts is disabled on this system"*, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again.

`requirements.txt` (you already have it) lists only the **direct** dependency:
```
fastapi[standard]
```
We don't paste the whole `pip freeze` output: that would pin dozens of transitive packages by hand.
In a later step we'll pin versions properly (lock file) for reproducible Docker builds.

## 🧩 Code, piece by piece

### 1. The app object
**Where:** `apps/api/app/main.py`: replace the `app = ...` line (and delete the TODO comments).

```python
from fastapi import FastAPI

app = FastAPI(title="Sentinel API")
```
`FastAPI(...)` creates the application: a registry of routes plus the OpenAPI schema it generates for
`/docs`. Uvicorn will look for this exact variable name (`app`). The `title` shows up in the docs page.

### 2. The first route
**Where:** same file, replace the `root()` function.

```python
@app.get("/")
def root():
    return {"message": "Sentinel API is running"}
```
The decorator registers `root()` as the handler for `GET /`. Returning a `dict` is enough: FastAPI
serialises it to JSON and sets `Content-Type: application/json` for you.

### 3. `.gitignore`
**Where:** repo root `.gitignore` (currently empty). Paste:

```gitignore
# Python
.venv/
__pycache__/
*.pyc

# Secrets: never commit
.env
.env.*
!.env.example
```
The venv is machine-specific and huge, and `__pycache__` is compiled bytecode Python regenerates itself,
so neither belongs in git. `.env` will hold API keys from step 1.5. The `!.env.example` line re-allows a
template file with fake values, which is a common pattern.

### 4. Remove the already-committed cache files
The `.pyc` files were committed before the `.gitignore` existed, so git still tracks them. Untrack them
(this keeps the files on disk and only removes them from git):

```powershell
cd ../..    # back to repo root
git rm -r --cached apps/api/app/__pycache__
git status
```
Expected: `deleted: apps/api/app/__pycache__/...pyc` (2 files) staged, and **no** `.venv` in the list.

## 📚 Key concepts
- **Uvicorn vs FastAPI**: FastAPI is the framework (it decides *what* to answer). Uvicorn is the ASGI
  server (it listens on a port and hands requests to the app). Keeping them separate lets you swap or
  tune the server (workers, ports) without touching app code. [FastAPI](https://fastapi.tiangolo.com/tutorial/first-steps/) · [Uvicorn](https://www.uvicorn.org/)
- `uvicorn app.main:app` means *package `app` → module `main.py` → variable `app`*.

## 🔐 Security note
- Your repo is **public**: `.gitignore` for `.env` goes in *before* any key exists. Once a secret is pushed,
  deleting it isn't enough: it stays in git history and bots scrape GitHub for keys within minutes.
- `--reload` and `127.0.0.1` are **dev only**. In production (week 9) there's no reload, and the server
  binds to `0.0.0.0` inside a container behind the cluster's ingress.

## ✅ Check it works
From `apps/api/` with the venv active:
```powershell
uvicorn app.main:app --reload
```
Expected:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```
- http://127.0.0.1:8000 → `{"message":"Sentinel API is running"}`
- http://127.0.0.1:8000/docs → interactive docs titled **Sentinel API**

Then commit (from repo root):
```powershell
git add .gitignore apps/api/app/main.py
git commit -m "fix(api): implement hello world route and add .gitignore"
git push
```

## ➡️ Next step
**1.2: `/health` endpoint + first pytest test.** Tell Claude **"I finished step 1.1, please review"**.
