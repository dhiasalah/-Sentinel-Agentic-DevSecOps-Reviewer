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
