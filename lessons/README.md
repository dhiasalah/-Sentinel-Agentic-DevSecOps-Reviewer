# Lessons index

One file per step. Claude adds a line here each time a new lesson is created.
Concept deep-dives go in `lessons/concepts/`.

## Week 1 — Foundations
- [1.0 Getting started — tools + repo structure](week01/00-getting-started.md)
- [1.1 Python venv + FastAPI hello world](week01/01-fastapi-hello-world.md)
- [1.2 `/health` endpoint + first pytest test](week01/02-health-and-tests.md)
- [1.3 Dockerfile for the API](week01/03-dockerfile.md)
- [1.4 Docker Compose (API + Redis)](week01/04-docker-compose.md)
- [1.5 API keys + `.env` / secrets handling](week01/05-secrets-and-env.md)
- [1.6 Oracle Cloud sign-up (account hardening)](week01/06-oracle-cloud-signup.md)

## Week 2 — First agent
- [2.1 Semgrep scan → JSON → `Finding` models](week02/01-semgrep-scan.md)
- [2.2 LLM router: Gemini primary, Groq fallback](week02/02-llm-router.md)
- [2.3 LLM triage (Part A): structured, validated, untrusted-aware](week02/03-llm-triage.md)
- [2.3 LLM triage (Part B): red-team your triage + policy layer](week02/03b-triage-red-team.md)
- [2.4 CLI: `python -m sentinel scan` + exit codes](week02/04-cli.md)

## Week 3 — GitHub App
- [3.1 Create the GitHub App (minimal permissions) + app JWT](week03/01-github-app.md)
- [3.2 Verify webhook signatures (`POST /webhooks/github`) + smee client](week03/02-webhook-signatures.md)
- [3.3 Installation token (downscoped) + clone the PR's commit + scan it](week03/03-installation-token-and-clone.md)
- [3.4 Redis queue + worker (replay-safe, no lost jobs)](week03/04-redis-queue-and-worker.md)

## Week 4 — Posting results
- [4.1 Worker posts the report as a PR comment (safe Markdown, upsert, write-only token)](week04/01-pr-comment.md)
- [4.2 Benchmark: 15 planted vulns + 4 decoys + answer key (Part A)](week04/02-benchmark-repo.md)
- [4.2 Benchmark grader: detection, right CWE, severity, decoys (Part B)](week04/03-benchmark-scorer.md)
- [4.3 Record the first demo GIF (storyboard, trimming, redaction checklist)](week04/04-demo-gif.md)
- [5.1 LangGraph skeleton: plan → parallel scanners → triage (workflow vs agent)](week05/01-langgraph-skeleton.md)
- [5.2 Part A: gitleaks secret scanning, custom rule, unsilenceable scan, secrets hidden from the LLM](week05/02-gitleaks-secrets.md)

## Concepts
- [AI security from zero: what lesson 2.3 really does](concepts/ai-security-from-zero.md) ← start here
- [Triage security explained simply (2.3)](concepts/triage-security-explained.md)
- [GitHub App + webhooks explained from zero (3.1 + 3.2)](concepts/github-app-and-webhooks-explained.md)
- [Week 3: what to remember + real examples of Redis/workers](concepts/week03-what-to-remember.md)
