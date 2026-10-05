import pytest

from sentinel import sandbox
from sentinel.graph import ScannerSpec
from sentinel.models import Finding, TriagedIssue
from sentinel.sandbox import SandboxError, verify_fix

CODE = "import yaml\n\n\ndef load(text):\n    return yaml.load(text, Loader=yaml.Loader)\n"
SAFE = CODE.replace("yaml.load(text, Loader=yaml.Loader)", "yaml.safe_load(text)")
FINDING = Finding(tool="semgrep", rule_id="yaml-load", severity="ERROR", message="m", file="app.py", line=5)
ISSUE = TriagedIssue(title="Unsafe YAML", severity="high", false_positive=False, explanation="e", fix="f",
                     findings=[FINDING])


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "app.py").write_text(CODE)
    return tmp_path / "repo"


def patched(files: dict[str, str | None]):
    def fake_apply(work, patch_dir):
        assert (patch_dir / "fix.patch").read_text() == "the diff"
        for name, text in files.items():
            if text is None:
                (work / name).unlink()
            else:
                (work / name).write_text(text)
    return fake_apply


def scanners(*found: Finding, fail=False):
    def run(path):
        if fail:
            raise RuntimeError("docker is down")
        return list(found)
    return {"semgrep": ScannerSpec(run=run, files=("*.py",))}


def verify(repo, monkeypatch, files, found=(), fail=False):
    monkeypatch.setattr(sandbox, "apply_patch", patched(files))
    return verify_fix(repo, "the diff", ISSUE, [FINDING], scanners(*found, fail=fail))


def test_a_real_fix_is_verified_and_the_repo_is_untouched(repo, monkeypatch):
    result = verify(repo, monkeypatch, {"app.py": SAFE})
    assert result.verified and result.changed == ["app.py"] and result.scanners == ["semgrep"]
    assert (repo / "app.py").read_text() == CODE


def test_the_vulnerability_still_reported_is_not_verified(repo, monkeypatch):
    result = verify(repo, monkeypatch, {"app.py": CODE.replace("Loader)", "UnsafeLoader)")}, [FINDING])
    assert not result.verified and result.still_there == [FINDING]


def test_a_new_finding_is_not_verified(repo, monkeypatch):
    leak = Finding(tool="semgrep", rule_id="hardcoded-token", severity="ERROR", message="m", file="app.py", line=5)
    result = verify(repo, monkeypatch, {"app.py": SAFE}, [leak])
    assert not result.verified and result.new == [leak]


def test_a_fix_that_breaks_the_syntax_is_not_scanned(repo, monkeypatch):
    result = verify(repo, monkeypatch, {"app.py": "def load(text:\n"}, fail=True)
    assert not result.verified
    assert result.problems == ["app.py no longer parses (line 1): scanners would be blind"]


def test_a_scanner_failure_is_not_verified(repo, monkeypatch):
    result = verify(repo, monkeypatch, {"app.py": SAFE}, fail=True)
    assert result.problems == ["scanner semgrep failed (RuntimeError)"]


@pytest.mark.parametrize("files, reason", [
    ({"app.py": None}, "only edits are allowed"),
    ({"app.py": SAFE, "evil.py": "x"}, "only edits are allowed"),
    ({}, "changes nothing"),
])
def test_deleting_adding_or_changing_nothing_is_rejected(repo, monkeypatch, files, reason):
    with pytest.raises(SandboxError, match=reason):
        verify(repo, monkeypatch, files)


def test_a_file_outside_the_issue_is_rejected(repo, monkeypatch):
    (repo / "other.py").write_text("x = 1\n")
    with pytest.raises(SandboxError, match="outside the issue"):
        verify(repo, monkeypatch, {"app.py": SAFE, "other.py": "x = 2\n"})


def test_git_runs_locked_down(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        raise SandboxError("stop")

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    with pytest.raises(SandboxError):
        sandbox.apply_patch(tmp_path, tmp_path)
    cmd = " ".join(seen["cmd"])
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "--user 65534:65534", "/patch:ro", "@sha256:"):
        assert flag in cmd
