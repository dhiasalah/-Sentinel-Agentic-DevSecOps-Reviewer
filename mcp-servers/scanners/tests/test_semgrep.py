import re

import pytest

from sentinel_scanners import semgrep
from sentinel_scanners.semgrep import parse_findings, run_semgrep
from sentinel_scanners.staging import CONFIG_DIR

SAMPLE = {
    "results": [
        {
            "check_id": "python.lang.security.audit.subprocess-shell-true",
            "path": "/src/app.py",
            "start": {"line": 24, "col": 12},
            "extra": {
                "message": "  shell=True is dangerous  ",
                "severity": "ERROR",
                "metadata": {"cwe": "CWE-78: OS Command Injection"},
            },
        }
    ]
}


def test_parse_findings_normalizes_semgrep_output():
    [finding] = parse_findings(SAMPLE)
    assert finding.tool == "semgrep"
    assert finding.file == "app.py"
    assert finding.line == 24
    assert finding.message == "shell=True is dangerous"
    assert finding.cwe == ["CWE-78: OS Command Injection"]


def test_parse_findings_handles_no_results():
    assert parse_findings({"results": []}) == []


@pytest.fixture
def captured(monkeypatch):
    jobs = []
    monkeypatch.setattr(semgrep, "run_job", jobs.append)
    return jobs


def test_scan_uses_our_rules_and_ignores_inline_nosemgrep(tmp_path, captured):
    assert run_semgrep(tmp_path) == {"results": []}
    [job] = captured
    for flag in ("--disable-nosem", "--config", "p/python", "/config/semgrep-rules.yaml"):
        assert flag in job.args
    assert not any(m.target == "/src/.semgrepignore" for m in job.mounts)


def test_repo_semgrepignore_is_shadowed_by_an_empty_one(tmp_path, captured):
    (tmp_path / ".semgrepignore").write_text("app/\n")
    run_semgrep(tmp_path)
    [shadow] = [m for m in captured[0].mounts if m.target == "/src/.semgrepignore"]
    assert shadow.path.name == "empty" and shadow.read_only is True


def test_refuses_a_semgrepignore_that_is_not_a_plain_file(tmp_path, captured):
    (tmp_path / ".semgrepignore").mkdir()
    with pytest.raises(RuntimeError, match="not a regular file"):
        run_semgrep(tmp_path)
    assert captured == []


def test_every_sentinel_rule_names_a_cwe():
    rules = (CONFIG_DIR / "semgrep-rules.yaml").read_text()
    ids = re.findall(r"^  - id: (sentinel\.\S+)$", rules, re.M)
    assert len(ids) == 5
    assert len(re.findall(r'cwe: \["CWE-\d+: ', rules)) == len(ids)
