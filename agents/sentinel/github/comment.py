import re

import httpx

from sentinel.config import Settings
from sentinel.github.auth import (GITHUB_API, HEADERS, get_app_info, get_installation_token, load_private_key,
                                  make_app_jwt, raise_for_github_error)
from sentinel.models import ScannerFailure, TriagedIssue

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


def render_comment(issues: list[TriagedIssue], finding_count: int, head_sha: str,
                   failures: list[ScannerFailure] = (), hidden: int = 0) -> str:
    lines = [MARKER, f"## 🛡️ Sentinel security report for `{head_sha[:7]}`", ""]
    if failures:
        names = ", ".join(sorted(f.scanner for f in failures))
        lines += [f"> ⚠️ **Scan incomplete:** {md_escape(names, 200)} failed, so this report may be missing issues. "
                  "Re-run the scan before merging.", ""]
    if not issues and hidden:
        lines.append("No issues at or above this repository's report threshold.")
    elif not issues:
        lines.append("No issues found by the scanners that ran." if failures else "No issues found. ✅")
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
    if hidden:
        lines += ["", f"{hidden} lower-severity issue(s) hidden by this repository's report threshold "
                      "(see the Sentinel dashboard)."]
    return "\n".join(lines)


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
                issues: list[TriagedIssue], finding_count: int, failures: list[ScannerFailure],
                settings: Settings, hidden: int = 0) -> str:
    app_jwt = make_app_jwt(settings.github_app_id, load_private_key(settings.github_private_key_path))
    bot_login = get_app_info(app_jwt)["slug"] + "[bot]"
    token = get_installation_token(app_jwt, installation_id, repo.split("/")[1], {"pull_requests": "write"})
    return upsert_comment(token, repo, pr, render_comment(issues, finding_count, head_sha, failures, hidden), bot_login)
