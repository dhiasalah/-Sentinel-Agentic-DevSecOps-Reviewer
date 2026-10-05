import ast
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from sentinel.models import Finding, TriagedIssue
from sentinel.planner import choose_scanners

if TYPE_CHECKING:
    from sentinel.graph import ScannerSpec

log = logging.getLogger(__name__)

GIT_IMAGE = "alpine/git:v2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26"
LOCKED_DOWN = [
    "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
    "--pids-limit", "64", "--memory", "256m", "--cpus", "1", "--user", "65534:65534",
]


class SandboxError(Exception):
    """The patch could not be tested."""


class Verification(BaseModel):
    changed: list[str]
    scanners: list[str]
    still_there: list[Finding] = []
    new: list[Finding] = []
    problems: list[str] = []

    @property
    def verified(self) -> bool:
        return not (self.still_there or self.new or self.problems)


def snapshot(root: Path) -> dict[str, str]:
    state = {}
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            state[rel] = ("link:" + os.readlink(path) if path.is_symlink()
                          else hashlib.sha256(path.read_bytes()).hexdigest())
    return state


def apply_patch(work: Path, patch_dir: Path) -> None:
    proc = subprocess.run([
        "docker", "run", "--rm", *LOCKED_DOWN,
        "-v", f"{work}:/work", "-v", f"{patch_dir}:/patch:ro", "-w", "/work",
        GIT_IMAGE, "apply", "--verbose", "/patch/fix.patch",
    ], capture_output=True, encoding="utf-8", timeout=60)
    if proc.returncode != 0:
        raise SandboxError(f"patch does not apply: {proc.stderr.strip()[-300:]}")


def key(f: Finding) -> tuple[str, str, str]:
    return f.tool, f.rule_id, f.file


def verify_fix(repo: Path, diff: str, issue: TriagedIssue, all_findings: list[Finding],
               scanners: dict[str, "ScannerSpec"]) -> Verification:
    with tempfile.TemporaryDirectory(prefix="sentinel-sandbox-") as tmp:
        work, patch_dir = Path(tmp) / "repo", Path(tmp) / "patch"
        shutil.copytree(repo, work, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        patch_dir.mkdir()
        (patch_dir / "fix.patch").write_text(diff, encoding="utf-8", newline="")

        before = snapshot(work)
        apply_patch(work, patch_dir)
        after = snapshot(work)

        if before.keys() != after.keys():
            added, removed = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
            raise SandboxError(f"patch adds {added} or removes {removed}: only edits are allowed")
        changed = sorted(name for name in after if after[name] != before[name])
        if not changed:
            raise SandboxError("patch changes nothing")
        if outside := sorted(set(changed) - {f.file for f in issue.findings}):
            raise SandboxError(f"patch changes files outside the issue: {outside}")
        if links := [name for name in changed if after[name].startswith("link:")]:
            raise SandboxError(f"patch turns files into symlinks: {links}")

        names = choose_scanners({name: spec.files for name, spec in scanners.items()}, changed)
        result = Verification(changed=changed, scanners=names)
        for name in changed:
            if name.endswith(".py"):
                try:
                    ast.parse((work / name).read_bytes(), filename=name)
                except SyntaxError as e:
                    result.problems.append(f"{name} no longer parses (line {e.lineno}): scanners would be blind")
        if result.problems:
            return result

        found: list[Finding] = []
        for name in names:
            try:
                found += scanners[name].run(work)
            except Exception as e:
                log.exception("sandbox: scanner %s failed", name)
                result.problems.append(f"scanner {name} failed ({type(e).__name__})")

    found = [f for f in found if f.file in changed]
    old = Counter(key(f) for f in all_findings if f.file in changed and f.tool in names)
    now = Counter(key(f) for f in found)
    fixed = Counter(key(f) for f in issue.findings)
    result.still_there = [f for f in found if key(f) in fixed and now[key(f)] > old[key(f)] - fixed[key(f)]]
    result.new = [f for f in found if now[key(f)] > old[key(f)]]
    return result
