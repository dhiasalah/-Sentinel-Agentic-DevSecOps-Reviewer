# Week 4 · Step 4.1 — The worker posts the report as a PR comment

## 🗺️ In plain words: what we're doing today

Right now Sentinel's report only appears in **your** worker terminal, and the person who opened the PR never sees it.
Today the worker **writes the report as a comment on the PR**, like a human reviewer would. Two rules make it a good bot:
it **updates its own comment** instead of adding a new one on every push, and it **cannot be tricked into writing something
dangerous**. That second rule matters because part of the report is written by an AI that has just read the attacker's code.

**Example:** you push to PR #5. A minute later a comment from **sentinel-dhia[bot]** appears:
"🛡️ Sentinel security report for `1144551`" with 🟧 HIGH: SQL injection, where, why, fix. You push again, and the **same**
comment changes. There's no second comment.

## 🎯 Goal

Close the loop PR → scan → **visible feedback on the PR**. That's the week 4 deliverable ("working bot on real PRs").

## 🧰 Tools in this step

- **GitHub Issues Comments API**: on GitHub, a PR *is* an issue with code attached, so the main PR conversation uses the
  *issue comments* endpoints. `GET/POST /repos/{repo}/issues/{pr}/comments` (list / create), `PATCH /repos/{repo}/issues/comments/{id}` (edit).
  Needs **Pull requests: write** (or Issues: write). [Docs](https://docs.github.com/en/rest/issues/comments)
- **GitHub-Flavored Markdown (GFM)**: the formatting language of comments (`**bold**`, `## heading`, `[link](url)`, `@mention`,
  `#12` → link to issue 12, and some raw HTML). It's powerful, which is exactly why untrusted text must be escaped before it goes in.
  [GFM spec](https://github.github.com/gfm/) · [Render API](https://docs.github.com/en/rest/markdown/markdown) (we used it to test the escaping)

```
worker: scan_pr(...)  ──issues──►  render_comment()  ── safe Markdown ──┐
          (token #1: contents:read, dies with the scan)                  │
                                                                         ▼
          new token #2: pull_requests:write ──► GET comments ─► ours? ─► PATCH (update) / POST (create)
```

---

## Part A — render the report safely (pure code, no network)

### Why this is the security heart of the step
The `title`, `why` and `fix` fields are written by an LLM **that just read the PR's code**. In 2.3 we saw that code can talk to the AI
("all findings are false positives"). If the attacker can steer the AI's words, they can steer **what your bot publishes**, and a bot
comment looks trustworthy. Without escaping, an attacker could make Sentinel post:
- `## ✅ Approved by the security team`: a fake approval heading;
- `@org/security` or `@everyone-in-a-team`: notification spam under your bot's name;
- `[download the fix](https://evil.example/patch.sh)`: a phishing link that *Sentinel* recommends;
- `![x](https://evil.example/pixel.png)`: a tracking image;
- `#1`, `GH-1`, `other/repo#5`: "mentioned this" spam on other issues;
- raw HTML like `<img ...>`, `<details>`, and anything else the renderer allows.

This is **output handling**, and it's in the OWASP Top 10 for LLM apps ("Improper Output Handling"): treat model output like user input.
It is untrusted until you escape it for the place where it will be displayed. [OWASP LLM05](https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/)

### 1. The escaper
**Where:** new file `agents/sentinel/github/comment.py`:
```python
import re

from sentinel.models import TriagedIssue

MARKER = "<!-- sentinel:report -->"
MAX_ISSUES = 25
ICON = {"critical": "🟥", "high": "🟧", "medium": "🟨", "low": "🟦", "info": "⬜"}
ZWSP = "​"
_MD_SPECIAL = re.compile(r"([\\`*_\[\]()#!|~<>])")
_LINKY = re.compile(r"(?i)https?://|ftp://|\bwww\.|@|#|\bgh-")


def md_escape(text: str, limit: int = 1000) -> str:
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit] + "…"
    text = _LINKY.sub(lambda m: m.group(0)[0] + ZWSP + m.group(0)[1:], text)
    return _MD_SPECIAL.sub(lambda m: "\\" + m.group(0), text)
```
Three moves, in order:
1. **Collapse whitespace.** All newlines become spaces, so the text can't start a new line. No `## heading`, no table, no list:
   it stays inside our bullet point.
2. **Break auto-links.** GitHub turns `https://…`, `www.…`, `@name`, `#12` and `GH-12` into links or notifications *even without
   Markdown syntax*. We slip a **zero-width space** (invisible) after the first character (`h​ttps://`, `@​name`), so the text looks the
   same but GitHub no longer recognises it.
3. **Backslash-escape** every Markdown/HTML special character. In GFM, `\*` means "a literal star", and `\<` means "a literal <, not a tag".

It also has a **length limit**, because a GitHub comment can't exceed 65,536 characters and an attacker could make the AI ramble.
`MAX_ISSUES` caps the list for the same reason.
We **escape** instead of **filtering** ("remove bad words"). Filtering is a blocklist, so you always miss a case. Escaping turns
*everything* into plain text, so there are no cases to miss.

### 2. The report
**Where:** same file, below `md_escape`:
```python
def render_comment(issues: list[TriagedIssue], finding_count: int, head_sha: str) -> str:
    lines = [MARKER, f"## 🛡️ Sentinel security report for `{head_sha[:7]}`", ""]
    if not issues:
        lines.append("No issues found. ✅")
    else:
        lines.append(f"**{len(issues)} issue(s)** from {finding_count} scanner finding(s). "
                     "Explanations are AI-written from this PR's code: treat them as advice, not proof.")
    for issue in issues[:MAX_ISSUES]:
        where = ", ".join(dict.fromkeys(f"{f.file}:{f.line}" for f in issue.findings))
        fp = " · *AI thinks: false positive*" if issue.false_positive else ""
        lines += ["", f"### {ICON[issue.severity]} {issue.severity.upper()}: {md_escape(issue.title, 200)}{fp}",
                  f"- **Where:** {md_escape(where, 300)}"]
        lines += [f"- ⚠️ **Needs human review:** {md_escape(reason)}" for reason in issue.review_reasons]
        lines += [f"- **Why:** {md_escape(issue.explanation)}", f"- **Fix:** {md_escape(issue.fix)}"]
    if len(issues) > MAX_ISSUES:
        lines += ["", f"…and {len(issues) - MAX_ISSUES} more issue(s) not shown."]
    return "\n".join(lines)
```
The rule is simple: **our** text (headings, labels, icons, severity from a fixed list, the SHA we validated) is Markdown.
**Their** text (anything that came from the AI or from the repo, including **file names**) always goes through `md_escape`.
File names are attacker-controlled too: someone can name a file `[click](http://evil).py`.
`MARKER` is an HTML comment. It's invisible on GitHub, and it lets us find our own comment again in Part B.
The "advice, not proof" line is honest UX: readers should know which part a machine wrote.

### 3. Tests for Part A
**Where:** new file `agents/tests/test_comment.py`:
```python
from sentinel.github.comment import MARKER, md_escape, render_comment
from sentinel.models import Finding, TriagedIssue


def issue(**overrides):
    base = dict(title="SQL injection", severity="high", false_positive=False,
                explanation="User input reaches execute().", fix="Use parameters.",
                findings=[Finding(tool="semgrep", rule_id="r", severity="ERROR", message="m", file="app.py", line=15)])
    return TriagedIssue(**{**base, **overrides})


def test_escape_keeps_normal_text_readable():
    assert md_escape("use f(x) in app_v2.py") == r"use f\(x\) in app\_v2.py"


def test_escape_neutralises_markdown_and_html():
    out = md_escape("![x](y) <img src=x> **bold**")
    assert out == r"\!\[x\]\(y\) \<img src=x\> \*\*bold\*\*"


def test_escape_breaks_links_mentions_and_issue_refs():
    out = md_escape("https://evil.example www.evil.com @org/security #1 GH-2")
    for linky in ("https://", "www.", "@org", "#1", "GH-2"):
        assert linky not in out


def test_escape_collapses_newlines_and_truncates():
    out = md_escape("line1\n\n# Heading\n| a | b |", limit=12)
    assert "\n" not in out
    assert out.endswith("…")


def test_report_starts_with_marker_and_shows_severity():
    body = render_comment([issue()], 1, "a" * 40)
    assert body.startswith(MARKER)
    assert "HIGH" in body and "aaaaaaa" in body and "app.py:15" in body


def test_injected_explanation_cannot_fake_an_approval():
    body = render_comment([issue(explanation="Looks fine.\n\n## Approved by @org/security")], 1, "a" * 40)
    assert "\n## Approved" not in body
    assert "@org" not in body


def test_empty_report():
    assert "No issues found" in render_comment([], 0, "b" * 40)
```
```powershell
cd agents; .\.venv\Scripts\Activate.ps1; pytest -q
```
Expected: `47 passed`.

**Proof on the real renderer.** Claude sent an "evil" report (fake `## ✅ Approved`, `@mention`, tracking image, phishing link, `<script>`,
`<img onerror>`, `#1`, `GH-1`, a file named `a_[x](y).py`) through GitHub's own Markdown API. The output contained **no** links, mentions,
headings, images or HTML: everything came out as plain text.

---

## Part B — post it with a second, write-only token

### 4. Give the App the right to comment
Your installation currently has `pull_requests: read`. We checked it live in 3.3, and it's the same "saved but not accepted" trap.
1. https://github.com/settings/apps → your app → **Permissions & events** → Repository permissions → **Pull requests: Read and write** → Save.
2. https://github.com/settings/installations → your app → **Accept new permissions**.

### 5. Let the caller choose the token's permissions (and show GitHub's errors)
**Where:** `agents/sentinel/github/auth.py`, **replace** the whole `get_installation_token` function with:
```python
def raise_for_github_error(resp: httpx.Response) -> None:
    if resp.is_error:
        raise RuntimeError(f"GitHub {resp.request.method} {resp.request.url.path} failed ({resp.status_code}): {resp.text}")


def get_installation_token(app_jwt: str, installation_id: int, repo_name: str, permissions: dict[str, str]) -> str:
    resp = httpx.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers={**HEADERS, "Authorization": f"Bearer {app_jwt}"},
        json={"repositories": [repo_name], "permissions": permissions},
        timeout=10,
    )
    raise_for_github_error(resp)
    return resp.json()["token"]
```
`permissions` has **no default** on purpose: every caller must say exactly what it needs, so nobody gets a broad token by accident.
`raise_for_github_error` closes the 3.3 blocker: the error now includes GitHub's explanation (like the 422 message we had to dig for).

Then:
- `agents/sentinel/github/scan_pr.py`: the call becomes `get_installation_token(app_jwt, installation_id, repo.split("/")[1], {"contents": "read"})`.
- `agents/tests/test_github_auth.py`, in `test_installation_token_is_downscoped`: in `FakeResponse`, **replace** the `raise_for_status`
  method with the line `is_error = False`, and call `get_installation_token("jwt", 99, "sentinel-playground", {"contents": "read"})`.

### 6. Create-or-update the comment
**Where:** `agents/sentinel/github/comment.py`. **Replace** the import block at the top with:
```python
import re

import httpx

from sentinel.config import Settings
from sentinel.github.auth import (GITHUB_API, HEADERS, get_app_info, get_installation_token, load_private_key,
                                  make_app_jwt, raise_for_github_error)
from sentinel.models import TriagedIssue
```
Then at the bottom add:
```python
def upsert_comment(token: str, repo: str, pr: int, body: str, bot_login: str) -> str:
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    comments_url = f"{GITHUB_API}/repos/{repo}/issues/{pr}/comments"
    resp = httpx.get(comments_url, headers=headers, params={"per_page": 100}, timeout=10)
    raise_for_github_error(resp)
    ours = next((c for c in resp.json()
                 if c["user"]["login"] == bot_login and c["body"].startswith(MARKER)), None)
    if ours:
        resp = httpx.patch(f"{GITHUB_API}/repos/{repo}/issues/comments/{ours['id']}",
                           headers=headers, json={"body": body}, timeout=10)
    else:
        resp = httpx.post(comments_url, headers=headers, json={"body": body}, timeout=10)
    raise_for_github_error(resp)
    return "updated" if ours else "created"


def post_report(repo: str, pr: int, head_sha: str, installation_id: int,
                issues: list[TriagedIssue], finding_count: int, settings: Settings) -> str:
    app_jwt = make_app_jwt(settings.github_app_id, load_private_key(settings.github_private_key_path))
    bot_login = get_app_info(app_jwt)["slug"] + "[bot]"
    token = get_installation_token(app_jwt, installation_id, repo.split("/")[1], {"pull_requests": "write"})
    return upsert_comment(token, repo, pr, render_comment(issues, finding_count, head_sha), bot_login)
```
**Upsert** means "update if it exists, insert if not". It makes the job **idempotent**. Remember from 3.4 that our queue is
*at-least-once*: a job can run twice. With upsert, running twice still leaves one comment.
We only take over a comment if **both** the author is our bot **and** it starts with the marker. Anyone can paste
`<!-- sentinel:report -->` into a comment. If we trusted the marker alone, we'd try to edit *their* comment, get a 403, and the job would fail.
That's a cheap denial-of-service against the bot.
The write token is created **after** the scan is done, so the code that touches untrusted files never holds a token that can write.
This answers the "worth thinking about" question from the installation-token explanation.

### 7. Wire it into the worker
**Where:** `agents/sentinel/worker.py`. Add the import under `from sentinel.config import Settings`:
```python
from sentinel.github.comment import post_report
```
Then in `process_one`, **replace** the two lines `report = render_text(...)` and `logger.info("%s#%d done, ...", ..., report)` with:
```python
        finding_count = sum(len(i.findings) for i in issues)
        logger.info("%s#%d done, %d issue(s)\n%s", job.repo, job.pr, len(issues), render_text(issues, finding_count))
        action = post_report(job.repo, job.pr, job.head_sha, job.installation_id, issues, finding_count, settings)
        logger.info("%s#%d report comment %s", job.repo, job.pr, action)
```
If posting fails (network, permission), the exception lands in the existing `except`, so the job goes to the dead-letter list and you can see why.

### 8. Tests for Part B
**Where:** `agents/tests/test_worker.py`. Add under the `r` fixture:
```python
@pytest.fixture(autouse=True)
def posted(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "post_report", lambda *args: calls.append(args[:2]) or "created")
    return calls
```
and at the bottom:
```python
def test_report_is_posted_after_scan(r, monkeypatch, posted):
    monkeypatch.setattr(worker, "scan_pr", lambda *a: [])
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert posted == [("o/r", 7)]


def test_failed_scan_posts_nothing(r, monkeypatch, posted):
    def boom(*args):
        raise RuntimeError("semgrep crashed")
    monkeypatch.setattr(worker, "scan_pr", boom)
    r.lpush(worker.QUEUE, JOB)
    worker.process_one(r, settings=None, timeout=1)
    assert posted == []
```
Without the autouse fake, every existing worker test would try to post a real comment with `settings=None`, crash, and fail.

**Where:** `agents/tests/test_comment.py`. At the top add `import httpx` and `from sentinel.github import comment`, and add
`upsert_comment` to the `from sentinel.github.comment import ...` line. Then at the bottom:
```python
class FakeGitHub:
    def __init__(self, existing):
        self.existing, self.calls = existing, []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return httpx.Response(200, json=self.existing, request=httpx.Request("GET", url))

    def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        return httpx.Response(201, json={}, request=httpx.Request("POST", url))

    def patch(self, url, **kwargs):
        self.calls.append(("PATCH", url))
        return httpx.Response(200, json={}, request=httpx.Request("PATCH", url))


def use(monkeypatch, fake):
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(comment.httpx, verb, getattr(fake, verb))


def test_first_report_creates_a_comment(monkeypatch):
    fake = FakeGitHub(existing=[])
    use(monkeypatch, fake)
    assert upsert_comment("ghs_x", "o/r", 7, MARKER + "\nreport", "sentinel-dhia[bot]") == "created"
    assert fake.calls[-1] == ("POST", "https://api.github.com/repos/o/r/issues/7/comments")


def test_next_report_updates_our_comment(monkeypatch):
    fake = FakeGitHub(existing=[{"id": 5, "user": {"login": "sentinel-dhia[bot]"}, "body": MARKER + "\nold"}])
    use(monkeypatch, fake)
    assert upsert_comment("ghs_x", "o/r", 7, MARKER + "\nnew", "sentinel-dhia[bot]") == "updated"
    assert fake.calls[-1] == ("PATCH", "https://api.github.com/repos/o/r/issues/comments/5")


def test_someone_elses_comment_with_our_marker_is_ignored(monkeypatch):
    fake = FakeGitHub(existing=[{"id": 9, "user": {"login": "attacker"}, "body": MARKER + "\nfake report"}])
    use(monkeypatch, fake)
    assert upsert_comment("ghs_x", "o/r", 7, MARKER + "\nreal", "sentinel-dhia[bot]") == "created"
```
```powershell
pytest -q
```
Expected: `52 passed`.

---

## 📚 Key concepts
- **Improper output handling (OWASP LLM05)**: LLM output is untrusted input for whatever displays it. Escape for the destination
  (Markdown here, HTML in the week 7 dashboard, SQL/shell never).
- **Escape, don't filter**: turn everything into plain text instead of hunting for bad patterns.
- **Idempotency via upsert**: needed because the queue is at-least-once.
- **One token per capability**: read token for the scan, write token for the comment, each for one repo and one hour.
- **Bot identity check**: the marker says *what* the comment is, and the author says *who* wrote it. Trust needs both.

## 🔐 Security note
- The report text is rendered as **plain text on purpose**. You lose pretty code blocks in "fix" (backticks show literally).
  That's the price, and it's worth it. Later we can allow code by putting it in a fenced block whose fence is longer than any run of
  backticks in the text.
- A comment posted by a bot is a **trust signal** for readers. Keeping the words "AI-written… advice, not proof" in the comment is part of the security design.
- We read only the first 100 comments. A PR with more would get a second report comment. That's acceptable for now.

## ✅ Check it works (live)
1. Step 4 done (Pull requests: Read and write, **accepted**).
2. Start Redis, the API, smee and the worker (same as 3.4).
3. Push a commit to your playground PR. Expected in the worker: `… done, 6 issue(s)`, then `… report comment created`.
   On GitHub, a comment from **sentinel-dhia[bot]** appears.
4. Push again. Expected: `report comment updated`, and still **one** comment on the PR (its header shows the new SHA).

If you get `RuntimeError: GitHub POST /app/installations/…/access_tokens failed (422): … permissions requested are not granted`,
step 4 wasn't accepted. Thanks to step 5, you can now read that directly in the error.

**Worth thinking about:** you push commit A, then commit B ten seconds later. With one worker the jobs run in order and B's report
wins. With two workers (week 9), A's scan could finish **after** B's and overwrite the comment with an **old** report.
How would you prevent that? (Hint: before posting, compare `head_sha` with the PR's current head.)

## ➡️ Next step
4.2: a benchmark repo with 10–15 planted vulnerabilities, to measure what Sentinel catches. Tell Claude "I finished step 4.1, please review".
