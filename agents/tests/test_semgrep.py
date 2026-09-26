from sentinel.scanners.semgrep import parse_findings

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
