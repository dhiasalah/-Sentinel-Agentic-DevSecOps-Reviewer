import subprocess

import pytest

from sentinel_scanners import gitleaks
from sentinel_scanners.gitleaks import parse_findings, run_gitleaks

SAMPLE = [{
    "RuleID": "hardcoded-secret-assignment",
    "Description": "Hardcoded secret assigned to a secret-looking variable",
    "StartLine": 5,
    "EndLine": 5,
    "Match": 'SECRET_KEY = "REDACTED"',
    "Secret": "REDACTED",
    "File": "/src/app/crypto.py",
}]


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

    monkeypatch.setattr(gitleaks.subprocess, "run", fake_run)
    return calls


def test_parse_findings_keeps_location_and_drops_the_secret():
    [finding] = parse_findings(SAMPLE)
    assert finding.tool == "gitleaks"
    assert finding.file == "app/crypto.py"
    assert (finding.line, finding.end_line) == (5, 5)
    assert finding.cwe == ["CWE-798"]
    assert "REDACTED" not in finding.model_dump_json()


def test_scan_is_offline_redacted_and_ignores_inline_allows(tmp_path, captured):
    assert run_gitleaks(tmp_path) == []
    cmd = " ".join(captured[0])
    for flag in ("--network none", "--redact", "--ignore-gitleaks-allow", "--config /config/gitleaks.toml"):
        assert flag in cmd
    assert ".gitleaksignore" not in cmd


def test_repo_ignore_file_is_shadowed_by_an_empty_one(tmp_path, captured):
    (tmp_path / ".gitleaksignore").write_text("/src/app/crypto.py:hardcoded-secret-assignment:5\n")
    run_gitleaks(tmp_path)
    assert f"{gitleaks.CONFIG_DIR / 'empty'}:/src/.gitleaksignore:ro" in captured[0]


def test_refuses_a_gitleaksignore_that_is_not_a_plain_file(tmp_path, captured):
    (tmp_path / ".gitleaksignore").mkdir()
    with pytest.raises(RuntimeError, match="not a regular file"):
        run_gitleaks(tmp_path)
    assert captured == []


def test_shadow_ignore_file_ships_with_sentinel():
    empty = gitleaks.CONFIG_DIR / "empty"
    assert empty.is_file()
    assert empty.stat().st_size == 0
