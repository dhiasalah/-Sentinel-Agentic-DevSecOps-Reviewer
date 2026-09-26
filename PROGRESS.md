# Sentinel — Learning Progress

> This file is the tutorial's memory. Claude reads it at the start of every session
> and updates it when a step is verified. You can edit it too.

## Current position
- **Week:** 1 — Foundations
- **Step:** 1.1 — Python venv + first FastAPI "hello world"
- **Lesson:** `lessons/week01/01-fastapi-hello-world.md`
- **Student level:** comfortable with code, learning AI/DevOps/security/deployment · **Mode:** copy-paste snippets + short explanations · **Language:** English

---

## Roadmap checklist
Weeks are broken into small steps when we reach them. Only Week 1 is detailed for now.

### Week 1 — Foundations
- [x] 1.0 Install and verify tools (Git, Python 3.12, Docker Desktop, VS Code) + `git init` + monorepo folders — *done 2026-09-23 (Python 3.13.5; repo pushed to GitHub)*
- [ ] 1.1 Python virtual environment + first FastAPI "hello world" (`apps/api`)
- [ ] 1.2 Add a `/health` endpoint + a first test with pytest
- [ ] 1.3 Write a Dockerfile for the API
- [ ] 1.4 Docker Compose (API + Redis) — `docker compose up` works
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

---

## Blockers / questions to revisit
- Repo is public on GitHub → be extra careful never to commit API keys (see step 1.5). Add a `.gitignore` in step 1.1.
