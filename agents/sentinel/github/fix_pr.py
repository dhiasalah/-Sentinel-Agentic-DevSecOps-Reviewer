import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

from sentinel.config import Settings
from sentinel.github.auth import (GITHUB_API, HEADERS, get_app_info, get_installation_token, load_private_key,
                                  make_app_jwt, raise_for_github_error)
from sentinel.github.checkout import checkout_pr_head, git_env, run_git
from sentinel.github.comment import md_escape

PR_RE = re.compile(r"^([A-Za-z0-9-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]{0,6})$")
FIX_ID_RE = re.compile(r"^fix-[0-9a-f]{8}$")


class PRMoved(Exception):
    """The pull request changed since the patch was made: the approval no longer matches it."""


def parse_pr(text: str) -> tuple[str, int]:
    match = PR_RE.fullmatch(text)
    if not match:
        raise ValueError("--pr must look like owner/repo#12")
    return match.group(1), int(match.group(2))


def installation_id(app_jwt: str, repo: str) -> int:
    resp = httpx.get(f"{GITHUB_API}/repos/{repo}/installation",
                     headers={**HEADERS, "Authorization": f"Bearer {app_jwt}"}, timeout=10)
    raise_for_github_error(resp)
    return resp.json()["id"]


def get_pr(token: str, repo: str, pr: int) -> dict:
    resp = httpx.get(f"{GITHUB_API}/repos/{repo}/pulls/{pr}",
                     headers={**HEADERS, "Authorization": f"Bearer {token}"}, timeout=10)
    raise_for_github_error(resp)
    data = resp.json()
    if data["state"] != "open":
        raise PRMoved(f"{repo}#{pr} is {data['state']}")
    if (data["head"]["repo"] or {}).get("full_name") != repo:
        raise ValueError(f"{repo}#{pr} comes from a fork: Sentinel only pushes to the repo it is installed on")
    return {"head_sha": data["head"]["sha"], "head_ref": data["head"]["ref"]}

def push_fix(repo: str, head_sha: str, diff: str, branch: str, message: str, bot: str, token: str) -> None:
    with checkout_pr_head(repo, head_sha, token) as work:
        env = git_env(token)
        patch = work / ".git" / "sentinel-fix.patch"
        patch.write_text(diff, encoding="utf-8", newline="")
        run_git(["apply", str(patch)], work, env)
        run_git(["-c", f"user.name={bot}", "-c", f"user.email={bot}@users.noreply.github.com",
                 "commit", "--quiet", "--all", "--no-verify", "-m", message], work, env)
        run_git(["push", "--quiet", "origin", f"HEAD:refs/heads/{branch}"], work, env)


def create_pull(token: str, repo: str, base: str, branch: str, title: str, body: str) -> str:
    resp = httpx.post(f"{GITHUB_API}/repos/{repo}/pulls",
                      headers={**HEADERS, "Authorization": f"Bearer {token}"},
                      json={"title": title, "head": branch, "base": base, "body": body}, timeout=10)
    raise_for_github_error(resp)
    return resp.json()["html_url"]

def render_body(pr: int, head_sha: str, summary: str, patch_id: str, approved_by: str) -> str:
    return "\n".join([
        f"Automated fix for #{pr}, made for commit `{head_sha[:7]}`.",
        "",
        f"- **What the AI says it changed:** {md_escape(summary, 500)}",
        f"- **Verified:** the patch was applied in Sentinel's sandbox and the scanners re-ran on the copy.",
        f"- **Approved by:** {md_escape(approved_by, 100)} (patch `{patch_id}`)",
        "",
        "Read the diff before merging: the patch was written by an AI that read this repository's code.",
    ])


def open_fix_pr(repo: str, pr: int, head_sha: str, diff: str, fix_id: str, summary: str, patch_id: str,
                approved_by: str, settings: Settings) -> str:
    if not FIX_ID_RE.fullmatch(fix_id):
        raise ValueError(f"invalid fix id: {fix_id}")
    app_jwt = make_app_jwt(settings.github_app_id, load_private_key(settings.github_private_key_path))
    bot = get_app_info(app_jwt)["slug"] + "[bot]"
    token = get_installation_token(app_jwt, installation_id(app_jwt, repo), repo.split("/")[1],
                                   {"contents": "write", "pull_requests": "write"})
    current = get_pr(token, repo, pr)
    if current["head_sha"] != head_sha:
        raise PRMoved(f"{repo}#{pr} moved from {head_sha[:7]} to {current['head_sha'][:7]}: run propose again")
    branch = f"sentinel/{fix_id}"
    push_fix(repo, head_sha, diff, branch, f"fix: {summary[:200]}\n\nSentinel {fix_id}, patch {patch_id}", bot, token)
    return create_pull(token, repo, current["head_ref"], branch, f"Sentinel fix for #{pr}",
                       render_body(pr, head_sha, summary, patch_id, approved_by))


@contextmanager
def checkout_pr(pr_ref: str, settings: Settings) -> Iterator[tuple[Path, dict]]:
    repo, pr = parse_pr(pr_ref)
    app_jwt = make_app_jwt(settings.github_app_id, load_private_key(settings.github_private_key_path))
    token = get_installation_token(app_jwt, installation_id(app_jwt, repo), repo.split("/")[1],
                                   {"contents": "read", "pull_requests": "read"})
    head = get_pr(token, repo, pr)
    with checkout_pr_head(repo, head["head_sha"], token) as path:
        yield path, {"repo": repo, "pr": pr, "head_sha": head["head_sha"]}
