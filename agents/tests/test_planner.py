from sentinel import planner
from sentinel.planner import choose_scanners, list_files

TRIGGERS = {"gitleaks": ("*",), "semgrep": ("*.py",), "checkov": ("dockerfile*", "*.tf")}


def test_scanners_are_picked_from_the_files_present():
    assert choose_scanners(TRIGGERS, ["README.md"]) == ["gitleaks"]
    assert choose_scanners(TRIGGERS, ["app.py", "Dockerfile.prod"]) == ["checkov", "gitleaks", "semgrep"]
    assert choose_scanners(TRIGGERS, []) == []


def test_git_internals_are_not_the_code(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hook.py").write_text("x = 1")
    (tmp_path / "notes.txt").write_text("hi")
    assert list_files(tmp_path) == ["notes.txt"]


def test_too_many_files_means_run_everything(tmp_path):
    for i in range(5):
        (tmp_path / f"padding{i}.txt").write_text("")
    assert list_files(tmp_path, limit=3) is None
    assert choose_scanners(TRIGGERS, None) == ["checkov", "gitleaks", "semgrep"]


def test_unreadable_folder_means_run_everything(monkeypatch, tmp_path):
    def broken_walk(root, onerror):
        onerror(PermissionError("access denied"))
        yield from ()

    monkeypatch.setattr(planner.os, "walk", broken_walk)
    assert list_files(tmp_path) is None
