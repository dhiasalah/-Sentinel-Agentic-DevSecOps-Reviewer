# Sentinel — Learning Progress

> This file is the tutorial's memory. Claude reads it at the start of every session
> and updates it when a step is verified. You can edit it too.

## Current position
- **Week:** 1 — Foundations
- **Step:** 1.5 — API keys (Gemini, Groq) + `.env` handling
- **Lesson:** `lessons/week01/05-secrets-and-env.md`
- **Student level:** comfortable with code, learning AI/DevOps/security/deployment · **Mode:** copy-paste snippets + short explanations · **Language:** English

---

## Roadmap checklist
Weeks are broken into small steps when we reach them. Only Week 1 is detailed for now.

### Week 1 — Foundations
- [x] 1.0 Install and verify tools (Git, Python 3.12, Docker Desktop, VS Code) + `git init` + monorepo folders — *done 2026-09-23 (Python 3.13.5; repo pushed to GitHub)*
- [x] 1.1 Python virtual environment + first FastAPI "hello world" (`apps/api`) — *done 2026-09-26*
- [x] 1.2 Add a `/health` endpoint + a first test with pytest — *done 2026-09-26*
- [x] 1.3 Write a Dockerfile for the API — *done 2026-09-26 (image 278MB)*
- [x] 1.4 Docker Compose (API + Redis) — `docker compose up` works — *done 2026-09-26*
- [ ] 1.5 Get Gemini and Groq API keys + `.env` handling and `.gitignore` (never commit secrets)
- [ ] 1.6 Sign up for Oracle Cloud (start early, approval can take time)
- **Deliverable:** `docker compose up` runs the API locally

### Week 2 — First agent
- [ ] Run Semgrep on a test repo, capture JSON output
- [ ] LLM triage: deduplicate, explain, rank severity
- [ ] Simple LLM router (Gemini primary, Groq fallback)
- **Deliverable:** CLI tool that scans a local repo and prints a triaged report

### Week 3 — GitHub App
- [ ] Create GitHub App with minimal permissions
- [ ] Verify webhook signatures
- [ ] Clone PR diff on each event
- [ ] Add Redis queue + worker
- **Deliverable:** opening a PR triggers a scan (visible in logs)

### Week 4 — Posting results
- [ ] Worker posts a formatted review comment on the PR
- [ ] Build a benchmark repo with 10–15 planted vulnerabilities
- [ ] Record first demo GIF
- **Deliverable:** working bot on real PRs

### Week 5 — Multi-agent with LangGraph
- [ ] Move logic into LangGraph: planner → parallel scanner agents
- [ ] Wrap Trivy, gitleaks, Checkov as MCP servers
- **Deliverable:** all four scanners run in parallel on a PR

### Week 6 — Fixer, sandbox, approval
- [ ] Fixer agent generates patches
- [ ] Sandbox: no network, read-only FS, resource limits
- [ ] Human approval via LangGraph interrupts
- [ ] Open a fix PR after approval
- **Deliverable:** full loop from finding to fix PR

### Week 7 — Dashboard
- [ ] Next.js on Vercel with GitHub login
- [ ] Pages: repo list, scan details, approval screen
- [ ] Supabase Postgres with row-level security
- **Deliverable:** approve fixes from the web app

### Week 8 — Live view and polish
- [ ] Stream agent progress via SSE
- [ ] Settings page
- [ ] Per-repo score trend chart
- **Deliverable:** demo-ready web platform

### Week 9 — Cloud and DevOps
- [ ] Terraform provisions the Oracle VM
- [ ] Install k3s, write Helm charts, set up ArgoCD
- [ ] GitHub Actions: test → build → Trivy image scan → push to GHCR
- [ ] Sealed Secrets + network policies
- **Deliverable:** `git push` deploys automatically to the cluster

### Week 10 — Security, evaluation, showcase
- [ ] Prompt-injection test suite running in CI
- [ ] Run benchmark: detection rate + false positives
- [ ] Connect Langfuse Cloud for traces and cost
- [ ] README with diagrams, demo GIF, and results
- [ ] Short blog / LinkedIn post on the prompt-injection defenses
- **Deliverable:** public, deployed, documented project ready for the CV

---

## Session log
| Date | What was done | Concepts learned | Open questions |
|---|---|---|---|
| 2026-09-23 | Tutorial set up (CLAUDE.md, PROGRESS.md, lessons/) | — | — |
| 2026-09-23 | Step 1.0: tools installed, repo initialised, 8 folders with `.gitkeep`, first commit pushed to GitHub | Git tracks files not folders; stage (`add`) vs snapshot (`commit`) vs upload (`push`); containers = same environment everywhere | — |
| 2026-09-26 | Switched teaching mode to copy-paste snippets + short explanations. Step 1.1: FastAPI app with `GET /`, root `.gitignore` (venv, pycache, `.env`), untracked committed `.pyc` files | FastAPI vs Uvicorn; `git rm --cached`; ignore secrets before they exist | `.gitignore` uses `apps/api/.venv/` → won't cover future venvs in `agents/` etc. |
| 2026-09-26 | Step 1.2: `GET /health`, `requirements-dev.txt` (`-r requirements.txt` + pytest), 2 tests with `TestClient` — `2 passed` | Liveness vs readiness; in-process testing; keep test deps out of prod image; health endpoints must not leak info | `.gitignore` still `apps/api/.venv/` (not fixed yet) |
| 2026-09-26 | Step 1.3: Dockerfile (slim base, layer caching, non-root `appuser`, HEALTHCHECK on `/health`, exec-form CMD) + `.dockerignore`; image built | Build context; layer cache; non-root = least privilege ("master key vs room key"); no secrets in layers; 0.0.0.0 in containers | Asked for a simpler explanation of non-root user → added "plain words" note to lesson 03 |
| 2026-09-26 | Lessons now start with a "🧰 Tools in this step" section (user request). Step 1.4: `compose.yaml` (api + redis, private network, Redis not published, API on 127.0.0.1, healthcheck, named volume), `/ready` pings Redis → 503, monkeypatch test — `3 passed` | Docker Compose; Redis as job queue; env-var config (12-factor); liveness vs readiness; mocking with monkeypatch | Test file imports `app` twice (`from app.main import app` + `from app import main`) |

---

## Blockers / questions to revisit
- Repo is public on GitHub → be extra careful never to commit API keys (see step 1.5). `.gitignore` with `.env` added in step 1.1 ✅.
- `.gitignore`: change `apps/api/.venv/` → `.venv/` before creating venvs in other folders.
- Commit messages: keep them descriptive (`fix(api)` alone says nothing in `git log`).
