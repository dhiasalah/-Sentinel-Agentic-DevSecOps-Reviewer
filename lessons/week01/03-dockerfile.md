# Week 1 · Step 1.3 — Dockerfile for the API

## 🎯 Goal

Package the API into a Docker **image** that runs the same way on your laptop, in CI and on the Oracle
VM / k3s cluster (week 9). You build it with security in mind from the start: small base image,
non-root user, no secrets and no test code inside.

## 💻 Commands

Make sure Docker Desktop is running:

```powershell
docker version
```

Expected: both a `Client:` and a `Server:` section. If `Server` shows an error, start Docker Desktop and wait.

Create the two files (from `apps/api/`):

```powershell
New-Item Dockerfile, .dockerignore
```

## 🧩 Code, piece by piece

### 1. `.dockerignore`

**Where:** `apps/api/.dockerignore`

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
tests/
requirements-dev.txt
.env
.env.*
Dockerfile
.dockerignore
```

When you run `docker build`, Docker first sends the whole folder (the **build context**) to the build
engine. This file excludes things from that upload. Without it, your 100 MB+ `.venv` (built for
Windows, useless in Linux) gets sent every build, and worse, a local `.env` could get copied into
the image by `COPY . .`. Anyone who pulls the image can read it.

### 2. Base image and Python settings

**Where:** `apps/api/Dockerfile`, at the top.

```dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
```

`python:3.13-slim` matches your local Python and is a Debian image stripped of compilers and docs:
about 5x smaller than `python:3.13`, and fewer packages means fewer CVEs for Trivy to flag in week 9.
`PYTHONDONTWRITEBYTECODE` skips `.pyc` files (useless in a container). `PYTHONUNBUFFERED` makes
`print`/logs appear immediately in `docker logs` instead of sitting in a buffer. `WORKDIR` sets the
folder the next instructions run in (created automatically).

### 3. Dependencies first (layer caching)

**Where:** same file, below `WORKDIR`.

```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

Each instruction creates a cached **layer**. If a layer's input hasn't changed, Docker reuses it. By
copying only `requirements.txt` before the code, editing `main.py` does **not** re-trigger the slow
`pip install`, and rebuilds take seconds. `--no-cache-dir` stops pip from keeping its download cache in
the image (smaller image).

### 4. Non-root user + app code

**Where:** same file, below the `pip install`.

```dockerfile
RUN useradd --create-home --uid 1000 appuser

COPY --chown=appuser:appuser app/ ./app/

USER appuser
```

By default containers run as **root**. If an attacker gets code execution in your API (and Sentinel
will process untrusted PR content), root makes escaping the container or tampering with it much
easier. `USER appuser` drops privileges for everything after it, including the running server.
`--chown` makes the app files owned by that user instead of root.

> **In plain words:** root = the master key to the whole container. Your API only needs the key to its
> own room (`/app`). If a burglar (attacker) gets in through the API, they get whatever key the API holds.
> With `appuser` they're stuck in one room: they can't install tools, change system files or easily
> break out to your machine. We lose nothing, because the API never needed the master key.

### 5. Healthcheck + start command

**Where:** same file, at the bottom.

```dockerfile
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- `EXPOSE` is documentation only: it says "this app listens on 8000". It doesn't publish the port.
- `HEALTHCHECK` is where your `/health` endpoint pays off. Docker calls it every 30s and marks the
  container `healthy`/`unhealthy`. The slim image has no `curl`, so you use Python's stdlib (and avoid
  installing an extra tool).
- `--host 0.0.0.0`: inside a container, `127.0.0.1` means "only this container", so Docker's port
  forwarding couldn't reach it. `0.0.0.0` means "all interfaces of the container". There's no `--reload`
  because this is production-style.
- **Exec form** (`["...", "..."]`) runs uvicorn directly as PID 1, so it receives `docker stop`'s SIGTERM
  and shuts down cleanly. The shell form (`CMD uvicorn ...`) wraps it in `/bin/sh`, which swallows the
  signal: Docker waits 10s and then kills it.

## 📚 Key concepts

- **Image vs container**: the image is the frozen recipe result (like a class). A container is a running
  instance of it (like an object). One image, many containers.
- **Build context**: the folder you pass to `docker build`; only files inside it (minus `.dockerignore`) can be `COPY`'d.
- Docs: [Dockerfile reference](https://docs.docker.com/reference/dockerfile/) ·
  [Build best practices](https://docs.docker.com/build/building/best-practices/) ·
  [FastAPI in Docker](https://fastapi.tiangolo.com/deployment/docker/)

## 🔐 Security note

- **Secrets never go in images**: not in `COPY`, not in `ENV`, not in `ARG`. Layers are readable by anyone who
  pulls the image (`docker history`), even if a later layer deletes the file. Secrets come in at **runtime**
  (env vars in step 1.5, Sealed Secrets in week 9).
- Non-root + slim base + no test deps shrinks the **attack surface**. In week 9 Trivy will scan this image in CI.

## ✅ Check it works

Build (from the **repo root**; the last argument is the build context):

```powershell
docker build -t sentinel-api:dev apps/api
```

Expected, ending with something like:

```
 => exporting to image
 => => naming to docker.io/library/sentinel-api:dev
```

Run it:

```powershell
docker run --rm -d -p 8000:8000 --name sentinel-api sentinel-api:dev
```

`-p 8000:8000` maps _host port : container port_, `-d` runs it in the background, and `--rm` deletes the container when it stops.

Check:

```powershell
curl.exe http://127.0.0.1:8000/health
docker exec sentinel-api whoami
docker ps
```

Expected:

```
{"status":"ok"}
appuser
... sentinel-api:dev ... Up 40 seconds (healthy) ... 0.0.0.0:8000->8000/tcp  sentinel-api
```

(`(health: starting)` for the first few seconds, then `(healthy)`.) Use `curl.exe`, not `curl`,
because in Windows PowerShell `curl` is an alias for `Invoke-WebRequest`.

Try the cache: change the message in `main.py`, rebuild, and notice the `pip install` step says `CACHED`.

Stop it:

```powershell
docker stop sentinel-api
```

Commit (from repo root):

```powershell
git add apps/api/Dockerfile apps/api/.dockerignore
git commit -m "feat(api): add Dockerfile with non-root user and healthcheck"
git push
```

## ➡️ Next step

**1.4: Docker Compose (API + Redis).** Tell Claude **"I finished step 1.3, please review"**.
