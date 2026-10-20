from bench import render, summarize
from score import grade

V1 = {"id": "V01", "file": "a.py", "lines": [1, 1], "cwes": ["CWE-89"], "severity": "high", "title": "t", "scanner": "s"}
V2 = {"id": "V02", "file": "b.py", "lines": [1, 1], "cwes": ["CWE-78"], "severity": "high", "title": "t", "scanner": "s"}
DECOY = {"id": "D01", "file": "c.py", "lines": [1, 1], "why_safe": "w"}
KEY = {"vulns": [V1, V2], "decoys": [DECOY]}


def issue(file, false_positive=False):
    finding = {"tool": "s", "rule_id": "r", "severity": "ERROR", "message": "m", "file": file, "line": 1, "cwe": []}
    return {"title": "t", "severity": "high", "false_positive": false_positive,
            "explanation": "e", "fix": "f", "findings": [finding], "review_reasons": []}


def test_a_dismissed_vuln_is_not_caught_and_a_vuln_caught_once_is_flaky():
    runs = [grade(KEY, [issue("a.py"), issue("c.py")]), grade(KEY, [issue("a.py", false_positive=True)])]
    summary = summarize(runs)
    assert summary["caught"] == [1, 0]
    assert summary["flagged"] == [1, 0]
    assert summary["hits"] == {"V01": 1, "V02": 0}


def test_the_headline_is_the_worst_run_not_the_best():
    runs = [grade(KEY, [issue("a.py"), issue("b.py")]), grade(KEY, [issue("a.py")])]
    text = render(summarize(runs))
    assert "worst run 1/2 (50%)" in text
    assert "always caught   V01" in text and "flaky           V02" in text and "never caught    -" in text
