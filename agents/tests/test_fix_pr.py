import subprocess
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest

from sentinel.github import fix_pr
from sentinel.github.fix_pr import PRMoved, get_pr, open_fix_pr, parse_pr, push_fix, render_body

SHA = "a" * 40
SETTINGS = SimpleNamespace(github_app_id=1, github_private_key_path=None)


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.mark.parametrize("text", ["o/r", "o/r#0", "o/r#12abc", "o/r#1; rm -rf /", "../x#1",
                                  "https://github.com/o/r/pull/1"])
def test_bad_pr_reference_is_refused(text):
    with pytest.raises(ValueError):
        parse_pr(text)


def test_good_pr_reference():
    assert parse_pr("dhiasalah/sentinel-playground#12") == ("dhiasalah/sentinel-playground", 12)


def fake_pr(monkeypatch, state="open", head_repo="o/r", sha=SHA):
    data = {"state": state, "head": {"sha": sha, "ref": "feature", "repo": head_repo and {"full_name": head_repo}}}
    monkeypatch.setattr(fix_pr.httpx, "get",
                        lambda url, **kw: httpx.Response(200, json=data, request=httpx.Request("GET", url)))


def test_open_pr_gives_its_head(monkeypatch):
    fake_pr(monkeypatch)
    assert get_pr("ghs_x", "o/r", 7) == {"head_sha": SHA, "head_ref": "feature"}


@pytest.mark.parametrize("state, head_repo, error", [
    ("closed", "o/r", PRMoved),
    ("open", "attacker/r", ValueError),
    ("open", None, ValueError),
])
def test_closed_or_fork_pr_is_refused(monkeypatch, state, head_repo, error):
    fake_pr(monkeypatch, state=state, head_repo=head_repo)
    with pytest.raises(error):
        get_pr("ghs_x", "o/r", 7)


def test_a_moved_pr_gets_no_fix(monkeypatch):
    monkeypatch.setattr(fix_pr, "make_app_jwt", lambda *a: "jwt")
    monkeypatch.setattr(fix_pr, "load_private_key", lambda p: "pem")
    monkeypatch.setattr(fix_pr, "get_app_info", lambda jwt: {"slug": "sentinel-dhia"})
    monkeypatch.setattr(fix_pr, "installation_id", lambda jwt, repo: 1)
    monkeypatch.setattr(fix_pr, "get_installation_token", lambda *a: "ghs_x")
    monkeypatch.setattr(fix_pr, "get_pr", lambda *a: {"head_sha": "b" * 40, "head_ref": "feature"})
    monkeypatch.setattr(fix_pr, "push_fix", lambda *a: pytest.fail("must not push"))
    with pytest.raises(PRMoved, match="moved from aaaaaaa to bbbbbbb"):
        open_fix_pr("o/r", 7, SHA, "diff", "fix-1234abcd", "s", "p", "alice", SETTINGS)


def test_body_escapes_the_ai_summary():
    body = render_body(7, SHA, "done. ![x](https://evil.example) @org/security", "03cf51fe1631", "alice")
    assert "![x](" not in body and "@org" not in body and "#7" in body


def test_push_commits_the_patch_on_a_new_branch(tmp_path, monkeypatch):
    origin, seed = tmp_path / "origin.git", tmp_path / "seed"
    git("init", "--bare", "--quiet", str(origin), cwd=tmp_path)
    git("clone", "--quiet", str(origin), str(seed), cwd=tmp_path)
    (seed / "app.py").write_bytes(b"import yaml\nyaml.load(x)\n")
    git("add", ".", cwd=seed)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "--quiet", "-m", "init", cwd=seed)
    git("push", "--quiet", "origin", "HEAD", cwd=seed)
    head = git("rev-parse", "HEAD", cwd=seed)

    @contextmanager
    def local_checkout(repo, sha, token):
        work = tmp_path / "work"
        git("clone", "--quiet", str(origin), str(work), cwd=tmp_path)
        git("checkout", "--quiet", "--detach", sha, cwd=work)
        yield work

    monkeypatch.setattr(fix_pr, "checkout_pr_head", local_checkout)
    diff = "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n import yaml\n-yaml.load(x)\n+yaml.safe_load(x)\n"
    push_fix("o/r", head, diff, "sentinel/fix-1234abcd", "fix: safe_load", "sentinel-dhia[bot]", "ghs_x")

    branch = "refs/heads/sentinel/fix-1234abcd"
    assert git("show", f"{branch}:app.py", cwd=origin) == "import yaml\nyaml.safe_load(x)"
    assert git("log", "-1", "--format=%P %an", branch, cwd=origin) == f"{head} sentinel-dhia[bot]"
