# Week 3 · Step 3.3 — Installation token + clone the PR's code + scan it

## 🗺️ In plain words: what we're doing today
Your API now knows *"PR #4 was opened in `sentinel-playground`, commit `eb4bc40…`, contract `165735765`"*. But knowing isn't
seeing: Sentinel still has no copy of the code. Today we write the three moves the worker will make for every PR:
1. **Get a room key.** Show the master key (app JWT) and ask GitHub for a 1-hour key for contract `165735765`, restricted to
   *read code* on *this one repo*.
2. **Copy the code.** Download **exactly** commit `eb4bc40…` into a fresh temporary folder.
3. **Scan and clean up.** Run your week 2 pipeline (Semgrep + LLM triage) on that folder, then delete the folder.

**Example:** you run a short script with your real PR's values. It prints `checked out dhiasalah/sentinel-playground@eb4bc40 into C:\…\Temp\sentinel-…`,
then the same triaged report as `python -m sentinel scan`, then `removed C:\…\Temp\sentinel-…`. The code came from GitHub, not from your disk.

## 🎯 Goal
A function `scan_pr(repo, head_sha, installation_id, settings)` that goes from a webhook's facts to a list of `TriagedIssue`.
The Redis worker in 3.4 will call exactly this function.

## 🧰 Tools in this step
- **Installation access token**: the *room key* from 3.1. `POST /app/installations/{id}/access_tokens` with your JWT returns a
  `ghs_…` token valid 1 hour. You can **downscope** it: ask for fewer repos and fewer permissions than the installation has.
  [Docs](https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app)
- **git plumbing** (`init` / `fetch <sha>` / `checkout`): instead of `git clone` (all branches, all history), we fetch **one commit**,
  depth 1. That's faster and gives the exact code the PR points to. Needs git ≥ 2.31 for `GIT_CONFIG_COUNT` (you have 2.43).
  [git fetch](https://git-scm.com/docs/git-fetch) · [GIT_CONFIG_COUNT](https://git-scm.com/docs/git-config#Documentation/git-config.txt-GITCONFIGCOUNT)
- **`tempfile` + `@contextmanager`**: `with checkout_pr_head(...) as path:` gives you a folder that is **always** deleted afterwards,
  even if the scan crashes. [contextlib](https://docs.python.org/3/library/contextlib.html#contextlib.contextmanager)

```
job {repo, head_sha, installation_id}           (from 3.2 webhook; from Redis in 3.4)
   │
   ├─ make_app_jwt(.pem) ──► POST /app/installations/165735765/access_tokens
   │                           body: {repositories: [sentinel-playground], permissions: {contents: read}}
   │                        ◄── ghs_… token (1 h, read-only, 1 repo)
   │
   ├─ temp folder ──► git init → fetch --depth 1 origin <head_sha> → checkout (token sent as an HTTP header via env var)
   │
   ├─ run_semgrep(folder) → parse_findings → triage (week 2, unchanged)
   │
   └─ finally: delete temp folder
```

## 🧩 Code, piece by piece (in `agents/`)

### 1. Ask for a room key
**Where:** `agents/sentinel/github/auth.py`, add at the bottom
```python
def get_installation_token(app_jwt: str, installation_id: int, repo_name: str) -> str:
    resp = httpx.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers={**HEADERS, "Authorization": f"Bearer {app_jwt}"},
        json={"repositories": [repo_name], "permissions": {"contents": "read"}},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["token"]
```
Your app *has* `Pull requests: write` on the installation, but cloning doesn't need it. So we ask for a token that can **only read
code of this one repo**. If this token leaks (e.g. from an error message in the clone step), it can't post comments or touch another repo.
This is **downscoping**: least privilege per task, not just per app. In week 4 the "post comment" step will ask for its own token with
`pull_requests: write` only. `repo_name` is the short name (`sentinel-playground`), not `owner/name`.

### 2. The checkout
**Where:** new file `agents/sentinel/github/checkout.py`
```python
import base64
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def git_env(token: str) -> dict[str, str]:
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
    }


def run_git(args: list[str], cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, timeout=120)


def _force_remove(func, path, exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


@contextmanager
def checkout_pr_head(repo: str, head_sha: str, token: str) -> Iterator[Path]:
    if not REPO_RE.fullmatch(repo) or not SHA_RE.fullmatch(head_sha):
        raise ValueError("refusing to clone: invalid repo name or commit sha")
    workdir = Path(tempfile.mkdtemp(prefix="sentinel-"))
    try:
        env = git_env(token)
        run_git(["init", "--quiet"], workdir, env)
        run_git(["config", "core.symlinks", "false"], workdir, env)
        run_git(["remote", "add", "origin", f"https://github.com/{repo}.git"], workdir, env)
        run_git(["fetch", "--quiet", "--no-tags", "--depth", "1", "origin", head_sha], workdir, env)
        run_git(["checkout", "--quiet", "--detach", "FETCH_HEAD"], workdir, env)
        logger.info("checked out %s@%s into %s", repo, head_sha[:7], workdir)
        yield workdir
    finally:
        shutil.rmtree(workdir, onexc=_force_remove)
        logger.info("removed %s", workdir)
```
Line by line, the parts that matter:
- **Validate before use.** `repo` and `head_sha` come from a webhook. Signed, yes, but the PR author chose parts of it. A SHA is exactly
  40 hex chars, so anything else is rejected. That rules out argument injection like a "sha" of `--upload-pack=calc.exe`.
- **Why the SHA and not the branch name.** A branch can move between "webhook received" and "clone started" (the author pushes again).
  With the SHA you scan exactly the commit you'll comment on. Race conditions like this are called **TOCTOU** (time-of-check vs time-of-use).
- **Token via environment, not in the URL.** `https://x-access-token:TOKEN@github.com/...` would put the token in the process list
  (visible to other programs on the machine) and save it in `.git/config`. `GIT_CONFIG_*` env vars inject an HTTP header instead:
  nothing on the command line, nothing written to disk. The header is scoped to `https://github.com/` only, so git never sends it anywhere else.
- `GIT_TERMINAL_PROMPT=0`: if auth fails, git errors out instead of **hanging forever** waiting for a password nobody will type.
- `core.symlinks=false`: a malicious PR could add a symlink `secret.txt → C:\Users\USER\.sentinel\github-app.pem`. With this setting,
  git writes it as a plain text file containing the path. Your `read_snippet` from 2.3 would also block it (`resolve()` + `is_relative_to`).
  Two locks on the same door is **defense in depth**.
- `timeout=120`: a huge repo must not block the worker forever.
- **No submodules.** We never run `submodule update`. A submodule URL could point anywhere, including internal servers.
- `finally` + `_force_remove`: attacker-written code must not pile up on disk. On Windows, git's object files are read-only and
  `rmtree` would fail, so `_force_remove` clears the flag and retries (`onexc` needs Python ≥ 3.12, you have 3.13).

### 3. The whole pipeline in one function
**Where:** new file `agents/sentinel/github/scan_pr.py`
```python
from sentinel.config import Settings
from sentinel.github.auth import get_installation_token, load_private_key, make_app_jwt
from sentinel.github.checkout import checkout_pr_head
from sentinel.llm.router import build_router
from sentinel.models import TriagedIssue
from sentinel.scanners.semgrep import parse_findings, run_semgrep
from sentinel.triage import triage


def scan_pr(repo: str, head_sha: str, installation_id: int, settings: Settings) -> list[TriagedIssue]:
    if settings.github_app_id is None or settings.github_private_key_path is None:
        raise RuntimeError("GITHUB_APP_ID and GITHUB_PRIVATE_KEY_PATH must be set")
    app_jwt = make_app_jwt(settings.github_app_id, load_private_key(settings.github_private_key_path))
    token = get_installation_token(app_jwt, installation_id, repo.split("/")[1])
    with checkout_pr_head(repo, head_sha, token) as path:
        findings = parse_findings(run_semgrep(path))
        return triage(findings, path, build_router(settings))
```
Nothing new in the scanning part: it's your week 2 pipeline, just pointed at a temp folder instead of a local path.
The `return` sits **inside** the `with`: triage reads snippets from the files, so the folder must still exist. It's deleted right after.
The token lives only in a local variable: never logged, never stored, gone in 1 hour anyway.

### 4. Tests (no network, no git)
**Where:** `agents/tests/test_github_auth.py`. Add `import httpx` at the top, add `get_installation_token` to the
`from sentinel.github.auth import ...` line, then add at the bottom:
```python
def test_installation_token_is_downscoped(monkeypatch):
    calls = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"token": "ghs_fake"}

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    assert get_installation_token("jwt", 99, "sentinel-playground") == "ghs_fake"
    assert calls["url"].endswith("/app/installations/99/access_tokens")
    assert calls["json"] == {"repositories": ["sentinel-playground"], "permissions": {"contents": "read"}}
```
**Where:** new file `agents/tests/test_checkout.py`
```python
import base64

import pytest

from sentinel.github.checkout import checkout_pr_head, git_env

GOOD_SHA = "eb4bc404a1b7363d84a7947b064693c873a9735c"


@pytest.mark.parametrize("repo, sha", [
    ("dhiasalah/sentinel-playground", "--upload-pack=calc.exe"),
    ("dhiasalah/sentinel-playground", "main"),
    ("evil.com/x; rm -rf /", GOOD_SHA),
    ("../../etc", GOOD_SHA),
])
def test_bad_repo_or_sha_is_refused(repo, sha):
    with pytest.raises(ValueError):
        with checkout_pr_head(repo, sha, "ghs_fake"):
            pass


def test_token_goes_in_a_github_only_header():
    env = git_env("ghs_fake")
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraHeader"
    assert env["GIT_CONFIG_VALUE_0"] == "Authorization: Basic " + base64.b64encode(b"x-access-token:ghs_fake").decode()
    assert env["GIT_TERMINAL_PROMPT"] == "0"
```
The first test tries four hostile inputs and checks that **none** of them ever reaches git (validation happens before `mkdtemp`, so
no folder is even created). `parametrize` = one test function, four cases, each reported separately. The second test pins
the token plumbing so a future refactor can't quietly move it back into the URL.

## ✅ Check it works
1. Tests (from `agents/`, venv active):
```powershell
cd agents; .\.venv\Scripts\Activate.ps1; python -m pytest -q
```
Expected: `34 passed` (29 old + 1 token + 4 bad-input cases + 1 env).

2. Real run on your PR #4. Docker Desktop must be running (Semgrep). Paste into PowerShell from `agents/`:
```powershell
@'
import logging, sys
from sentinel.cli import render_text
from sentinel.config import Settings
from sentinel.github.scan_pr import scan_pr

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
sys.stdout.reconfigure(encoding="utf-8")
issues = scan_pr("dhiasalah/sentinel-playground", "eb4bc404a1b7363d84a7947b064693c873a9735c", 165735765, Settings())
print(render_text(issues, sum(len(i.findings) for i in issues)))
'@ | python -
```
Expected (details vary by LLM run):
```
INFO sentinel.github.checkout: checked out dhiasalah/sentinel-playground@eb4bc40 into C:\Users\USER\AppData\Local\Temp\sentinel-ab12cd
INFO httpx: HTTP Request: POST https://generativelanguage.googleapis.com/... "HTTP/1.1 200 OK"
INFO sentinel.github.checkout: removed C:\Users\USER\AppData\Local\Temp\sentinel-ab12cd
[HIGH    ] SQL injection in ...
  at:  app.py:24
...
9 scanner findings -> 5 issues
```
Then check the folder is really gone: `Test-Path C:\Users\USER\AppData\Local\Temp\sentinel-ab12cd` → `False`.

If you see:
- `401` on `access_tokens` → wrong App ID / key (like 3.1).
- `422 ... repositories` → the app isn't installed on that repo, or the repo name is misspelled.
- `CalledProcessError ... fetch` → the SHA doesn't exist in that repo (typo, or you force-pushed since).
- `0 findings` → the vulnerable Flask app isn't in that PR's commit. Check the playground repo has it.

## 📚 Key concepts
- **Downscoped credentials.** One app, but each task asks for the smallest token it needs. Blast radius per step, not per app.
- **Immutable references.** A SHA can't change, a branch can. Security decisions should be tied to immutable IDs.
- **Validate at the boundary.** Data from outside (even signed) gets checked against a strict pattern before it touches a shell, a path or git.
- **Ephemeral workspaces.** Untrusted code gets a fresh folder per job, deleted after. Nothing leaks from one PR to the next.

## 🔐 Security note
- **We read PR code, we never run it.** No `pip install`, no running tests, no `setup.py`. Running the author's code with your token
  in the environment = handing them the token. This is the classic `pull_request_target` mistake in GitHub Actions. When Sentinel
  needs to run anything from a PR (week 6 fixer), it happens in a sandbox with no network and no secrets.
- **Fork PRs** work too: GitHub keeps every PR's commits reachable from the base repo, so fetching the SHA from `repository` is enough.
  And the fork's author never gets your token.
- **Error messages.** `CalledProcessError` includes git's stderr. Git doesn't print the header, but never log raw exceptions from
  auth code without checking what's inside.
- Worth thinking about: the installation token lasts 1 hour, and a scan takes ~30 s. What's the downside of caching one token per installation
  for 55 minutes to save API calls, and when would that trade-off be worth it?

## ➡️ Next step
3.4: the webhook pushes the job into Redis (with replay de-duplication on `X-GitHub-Delivery`), and a worker process pops it and calls `scan_pr`.
Tell Claude "I finished step 3.3, please review".
