# Sentinel — Learning Progress

> This file is the tutorial's memory. Claude reads it at the start of every session
> and updates it when a step is verified. You can edit it too.

## Current position
- **Week:** 4 — Posting results
- **Step:** 4.2 — Benchmark repo with 10–15 planted vulnerabilities
- **Lesson:** `lessons/week04/02-benchmark-repo.md` (to be written)
- **Note:** user is a beginner in AI security → explain from zero, analogies + concrete examples (see `lessons/concepts/ai-security-from-zero.md`)
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
- [x] 1.5 Get Gemini and Groq API keys + `.env` handling and `.gitignore` (never commit secrets) — *done 2026-09-26*
- [x] 1.6 Sign up for Oracle Cloud (start early, approval can take time) — *done 2026-09-26 (home region Paris, MFA on, `sentinel` compartment, budget alert)*
- **Deliverable:** `docker compose up` runs the API locally ✅ **Week 1 complete**

### Week 2 — First agent
- [x] 2.1 Semgrep (in Docker) on a deliberately vulnerable demo app → parse JSON into `Finding` models (`agents/`) — *done 2026-09-26 (9 findings)*
- [x] 2.2 Simple LLM router (Gemini primary, Groq fallback) — *done 2026-09-27 (`gemini-3.8-flash` + `openai/gpt-oss-120b`, 6 tests)*
- [x] 2.3 LLM triage: deduplicate, explain, rank severity (structured output, PR code treated as untrusted) — *done 2026-09-27 (Part A + Part B policy layer, 22 tests, injection attack resisted + flagged)*
- [x] 2.4 CLI: scan a local repo and print the triaged report — *done 2026-09-27 (written by Claude at user's request; 28 tests)*
- **Deliverable:** CLI tool that scans a local repo and prints a triaged report ✅ **Week 2 complete**

### Week 3 — GitHub App
- [x] 3.1 Create GitHub App with minimal permissions (Contents R, Pull requests RW, event `pull_request`), playground repo, smee channel, key outside repo, app JWT — *done 2026-09-28 (app `sentinel-dhia`, 29 tests)*
- [x] 3.2 Verify webhook signatures (`POST /webhooks/github`, HMAC SHA-256, smee client forwards locally) — *done 2026-09-28 (10 API tests; real PR #4 → 202, unsigned POST → 401)*
- [x] 3.3 Installation token (downscoped to 1 repo + `contents: read`) + clone PR `head_sha` into a temp folder + scan it — *done 2026-09-29 (`scan_pr` end-to-end: 11 findings → 6 issues, 35 tests)*
- [x] 3.4 Redis queue + worker (body-hash replay de-dup, reliable queue with processing + dead-letter lists) — *done 2026-09-29 (live PR #5 queued → scanned, 13 API + 40 agent tests)*
- **Deliverable:** opening a PR triggers a scan (visible in logs) ✅ **Week 3 complete**

### Week 4 — Posting results
- [x] 4.1 Worker posts a formatted review comment on the PR (escaped Markdown, upsert by bot login + marker, separate `pull_requests: write` token) — *done 2026-09-30 (PR #7: created @ `566c466`, updated in place @ `6161737`, 52 tests)*
- [ ] 4.2 Build a benchmark repo with 10–15 planted vulnerabilities
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
| 2026-09-26 | Step 1.5: Gemini + Groq keys in root `.env` (ignored), `.env.example` committed, `config.py` with pydantic-settings + `SecretStr` (fail fast), `env_file` in compose, secret-masking test — `4 passed`; no keys in git history | Secret lifecycle; fail-fast config; SecretStr; env precedence (`environment` > `env_file`); YAML indentation = meaning (debugged `env_file` nested under `environment`) | `.gitignore` line 2 is `.venv/__pycache__/` (two rules merged) |
| 2026-09-26 | Step 1.6: Oracle Cloud account (home region Paris), MFA enabled, `sentinel` compartment, budget alert. Considered Azure for Students; kept Oracle | Cloud provider, region, tenancy/compartment, IAM, MFA, budget alerts, shared responsibility | 1.5 review fixes (`.gitignore` line 2, unused `import os`) still not committed |
| 2026-09-26 | Fixed `.gitignore` + unused import. Step 2.1: `agents/` project, `Finding` model, `run_semgrep` (Docker, read-only mount, list-form cmd, timeout), `parse_findings`, 2 unit tests; real scan = 9 findings | SAST; Semgrep rules/registry; normalization layer; CWE; unit vs integration tests; list-form subprocess vs shell injection | Scan results: duplicates (3 rules on line 24, 2 on 33, 2 for the SQLi), pickle + hardcoded password **missed** → input for 2.3 triage and for gitleaks (week 5). `run_semgrep` doesn't check the target exists (Docker creates an empty dir → silent 0 findings) |
| 2026-09-27 | Step 2.2: `Provider` protocol, `GeminiProvider` + `GroqProvider` (timeouts, no SDK retries), `LLMRouter` falls back only on `ProviderUnavailable` (429/5xx/network), 4 router tests with fakes — `6 passed`. Real calls: Gemini 200 OK; saw a real 503 → fallback. Both original models retired → switched to `gemini-3.8-flash` / `openai/gpt-oss-120b`. `is_dir()` fix in `run_semgrep` done | Provider abstraction; transient vs permanent errors (fallback on 429/5xx, raise on 404); model deprecation; pinned model vs `-latest` alias (reproducible evals); "listed ≠ accessible" | `config.py` default `groq_model` contains `"GROQ_MODEL=..."` (pasted whole line). Windows cp1252 console can crash on printing LLM output with Unicode (`‑`) |
| 2026-09-27 | Step 2.3 Part A: `json_mode` in providers/router (AFC disabled), `TriagedIssue`, `triage.py` (schema-limited LLM output, random-tag untrusted wrapper, path-traversal-safe snippets, fail-closed id checks), 7 tests — `13 passed`. Real run: 9 findings → 4–5 issues. Asked for a plain-language security explanation → `lessons/concepts/triage-security-explained.md` | Structured output; output validation; spotlighting; least authority for the LLM; fail closed; path traversal | Two runs gave different groupings/severities (MD5 medium vs high; debug/0.0.0.0 merged vs split) even at temperature 0 → need evals (week 10). Pickle still missed (triage can't add findings, by design). `at:` repeats the same line (cosmetic). LLM `fix` text contains Markdown code blocks → render safely in PR comments (week 4) |
| 2026-09-27 | User found lesson 2.3 too hard → wrote `concepts/ai-security-from-zero.md`. Step 2.3 Part B: `flask-injected` attack app, `policy.py` (severity floor from Semgrep, false positives kept + flagged, injection tripwire regex), `review_reasons` on `TriagedIssue`. Old sort test broke because the floor raised the fake AI's `low` → fixed the test (Claude edited it at user's request) — `22 passed`. Real attack: Gemini 503 → Groq; SQLi reported HIGH + "possible prompt injection" review flag | Prompt injection; red teaming; asymmetric risk (AI may escalate, humans de-escalate); test the guardrail, not the model; detection vs prevention; a new safety rule can legitimately break old tests | Only 1 attack × 1 run × 1 model so far → more attacks in the week 10 eval suite |
| 2026-09-27 | Step 2.4: user found the CLI step uninteresting and asked Claude to implement it. Claude wrote `cli.py` (argparse `scan` sub-command, `--format text/json`, `--fail-on`, `-v`), `__main__.py`, `test_cli.py`, removed the old `__main__` block from `triage.py` — `28 passed`. Real run: 9 findings → 5 issues, exit 1; missing folder → exit 2 | Exit codes as an API for CI (0 clean / 1 issues / 2 tool error, a crash must never be 0); stdout vs stderr | Who sets `--fail-on` (repo owner, not PR author) → week 8 settings |
| 2026-09-28 | Step 3.1: GitHub App `sentinel-dhia` (Contents R, PRs RW, `pull_request` event, own account only) on `sentinel-playground`, smee channel shows `pull_request`/`opened`, `.pem` in `~\.sentinel\` + `*.pem` ignored, `auth.py` (RS256 app JWT, iat-60s / exp+9min, httpx timeout), JWT test — `29 passed`; `GET /app` → `sentinel-dhia`. First live call 401 `"A JSON web token could not be decoded"` because `.env` kept the lesson's example `GITHUB_APP_ID=123456` → fixed | GitHub App vs PAT; two-level auth (app JWT = master key, installation token = room key); asymmetric signatures (GitHub keeps only the public key); webhooks = push; smee channels are public | Import order nit in `agents/sentinel/config.py` (`pathlib` between pydantic imports) |
| 2026-09-28 | Step 3.2: `GITHUB_WEBHOOK_SECRET` (required `SecretStr`), `webhooks.verify_signature` (HMAC SHA-256 on raw body, `compare_digest`, empty secret fails closed), `POST /webhooks/github` (verify → parse, `ping`, only opened/synchronize/reopened, logs job, 202), 6 attack tests — `10 passed`. Live: smee-client → real PR #4 accepted (installation 165735765), unsigned POST → 401. First attempt showed nothing because smee-client wasn't running | Why smee (localhost unreachable from GitHub, outbound connection); installation = one "contract" of the app, `installation_id` picks which room key to mint; HMAC (symmetric) vs JWT (asymmetric); verify-then-parse; ack fast (10 s) + queue; replay risk on a public smee channel | Replay de-dup by `X-GitHub-Delivery` → 3.4. Rate-limiting `synchronize` spam (denial-of-wallet) → later |
| 2026-09-29 | Step 3.3: `get_installation_token` (downscoped: 1 repo, `contents: read`), `checkout.py` (repo/sha regex validation, `init`+`fetch --depth 1 <sha>`+detached checkout, `core.symlinks false`, token via `GIT_CONFIG_*` extraHeader not URL, temp dir always removed), `scan_pr.py` glues token → checkout → semgrep → triage — `35 passed`. First live run: 422 `"The permissions requested are not granted to this installation."` — installation only had metadata/pull_requests/repository_hooks (Contents R from 3.1 was never actually saved/accepted) → user added Contents: Read-only + accepted on the installation → 201, token scoped to `sentinel-playground` with `contents`+`metadata` read, expires 1h. Real scan: 6 issues, Gemini 503 → Groq, injection app still flagged | Why installation token (JWT = identity only; installation = consent; short-lived, scoped vs PAT blast radius); downscoping can only shrink; permission changes need the installation owner to **accept**; 401/404/422 tell you which auth layer failed; token out of URLs/`.git/config` | `raise_for_status()` hides GitHub's error body → replace with `RuntimeError(f"... {resp.status_code}: {resp.text}")` in `auth.py`. Separate write-scoped token for PR comments (week 4)? |
| 2026-09-29 | Step 3.4: Redis published on `127.0.0.1:6379` only; API: `SET sentinel:seen:<sha256(body)> NX EX 24h` then `LPUSH sentinel:jobs`, 503 if Redis down; `sentinel/worker.py` (`Job` pydantic model, `BLMOVE` jobs→processing, `scan_pr`, dead-letter on any exception, `LREM` in `finally`, `requeue_stale` on start); fakeredis tests — API `13 passed`, agents `40 passed`. First live webhook crashed (`NameError: hashlib`, import step skipped). Live: PR #5 job sat in the queue while the worker was off (nothing lost), then the worker ran it → 6 issues, Gemini 503 → Groq, lists back to 0/0/0. Style fixes (duplicate `import pytest`, import order, PEP 8 blank lines, missing final newlines in requirements, compose blank line) applied by Claude at user's request | Async work via a queue (10 s webhook limit); reliable queue (atomic BLMOVE + processing list); at-least-once ⇒ idempotent jobs; dead-letter queue; replay de-dup must key on **signed** data (body), not headers; privilege separation (internet-facing API holds only the webhook secret); Redis has no auth by default | `requeue_stale` is only safe with one worker (week 9). Poison-pill loop if a job kills the process (count attempts). Same PR scored `debug=True` MEDIUM in 3.3 and HIGH now → evals (week 10). API `Settings` still requires Gemini/Groq keys it no longer needs → remove. Live Redeliver→`duplicate` and Ctrl+C→requeue not yet tried by user |
| 2026-09-30 | Step 4.1: `comment.py` (`md_escape`: collapse whitespace, zero-width space breaks auto-links/mentions/`#refs`, backslash-escape MD/HTML, length caps; `render_comment` with invisible marker; `upsert_comment`; `post_report` mints a separate `pull_requests: write` token after the scan), `raise_for_github_error` shows GitHub's error body, worker posts the report — `52 passed`. Live bug: worker crashed after 5 s with `redis TimeoutError` because redis-py 8.1 added a default `socket_timeout=5`, equal to the `BLMOVE` wait → `socket_timeout=30` + pinned `redis==8.1.0` (fixed by Claude at user's request). Live: PR #7 comment created @ `566c466`, then the same comment updated @ `6161737` (still 1 comment). Style fixes + `get_app_info` error body committed/pushed by Claude at user's request (`d2e61f4`) | Improper output handling (OWASP LLM05); escape, don't filter; upsert = idempotency for an at-least-once queue; one token per capability (read for the scan, write for the comment); trust needs author **and** marker; socket timeout must exceed the blocking-command timeout; unpinned dependencies change behaviour silently | Stale report race with 2+ workers (compare `head_sha` with the PR's current head before posting) → week 9. Other requirements still unpinned. `get_app_info` called on every job (cache later) |

---

## Blockers / questions to revisit
- Repo is public on GitHub → be extra careful never to commit API keys (see step 1.5). `.gitignore` with `.env` added in step 1.1 ✅.
- ~~`agents/sentinel/scanners/semgrep.py`: validate `target.is_dir()` before `docker run`~~ ✅ fixed in 2.2.
- ~~`agents/sentinel/config.py`: `groq_model` default~~ ✅ fixed (commit 9cba37a).
- ~~LLM output to a Windows console can raise `UnicodeEncodeError`~~ ✅ `cli.py` reconfigures stdout to UTF-8.
- Commit messages: keep them descriptive (`fix(api)` alone says nothing in `git log`).
- `apps/api/app/config.py`: API no longer needs `gemini_api_key`/`groq_api_key` (worker does) → drop them so the internet-facing service holds only the webhook secret.
- ~~`auth.py`: `raise_for_status()` hides GitHub's explanation~~ ✅ `raise_for_github_error` (4.1).
- Pin the remaining `agents/requirements.txt` / `apps/api/requirements.txt` versions (redis-py 8 broke the worker silently) → before the week 9 image builds.
- Worker must not post a stale report when 2+ workers run (check PR head SHA before posting) → week 9.
