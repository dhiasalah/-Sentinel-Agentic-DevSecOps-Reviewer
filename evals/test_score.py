from score import DEFAULT_KEY, decoy_flagged, grade, grade_vuln, load_json, unplanned

VULN = {"id": "V01", "file": "app/db.py", "lines": [5, 6], "cwes": ["CWE-89"], "severity": "high",
        "title": "SQL injection", "scanner": "semgrep"}
DECOY = {"id": "D01", "file": "app/db.py", "lines": [10, 10], "why_safe": "parameterised"}
KEY = {"vulns": [VULN], "decoys": [DECOY]}


def issue(file, line, severity="high", cwe="CWE-89: SQL Injection", false_positive=False):
    finding = {"tool": "semgrep", "rule_id": "r", "severity": "ERROR", "message": "m",
               "file": file, "line": line, "cwe": [cwe]}
    return {"title": "t", "severity": severity, "false_positive": false_positive,
            "explanation": "e", "fix": "f", "findings": [finding], "review_reasons": []}


def test_finding_anywhere_in_the_line_range_counts_even_with_windows_paths():
    result = grade_vuln(VULN, [issue("app\\db.py", 6)])
    assert result["found"] and result["cwe_ok"] and result["severity_ok"]


def test_wrong_line_or_wrong_file_is_a_miss():
    assert not grade_vuln(VULN, [issue("app/db.py", 7), issue("app/web.py", 5)])["found"]


def test_right_line_wrong_label_is_found_but_misdiagnosed():
    result = grade_vuln(VULN, [issue("app/db.py", 5, severity="medium", cwe="CWE-79: XSS")])
    assert result["found"]
    assert not result["cwe_ok"] and not result["severity_ok"]


def test_real_vuln_called_false_positive_is_found_but_dismissed():
    result = grade_vuln(VULN, [issue("app/db.py", 5, false_positive=True)])
    assert result["found"] and result["dismissed"]


def test_decoy_counts_as_flagged_only_if_the_ai_did_not_dismiss_it():
    assert decoy_flagged(DECOY, [issue("app/db.py", 10)])
    assert not decoy_flagged(DECOY, [issue("app/db.py", 10, false_positive=True)])


def test_issue_matching_nothing_is_unplanned():
    assert unplanned([issue("app/db.py", 5), issue("app/other.py", 1)], KEY) == 1


def test_empty_report_finds_nothing():
    result = grade(KEY, [])
    assert not result["vulns"][0]["found"] and result["decoys"] == {"D01": False}


def test_answer_key_points_at_real_lines_and_never_overlaps():
    key = load_json(DEFAULT_KEY)
    target = DEFAULT_KEY.parent / key["target"]
    seen = set()
    for item in key["vulns"] + key["decoys"]:
        first, last = item["lines"]
        line_count = len((target / item["file"]).read_text(encoding="utf-8").splitlines())
        assert 1 <= first <= last <= line_count, item["id"]
        spots = {(item["file"], n) for n in range(first, last + 1)}
        assert not spots & seen, f"{item['id']} overlaps another entry"
        seen |= spots
    for vuln in key["vulns"]:
        assert vuln["severity"] in {"critical", "high", "medium", "low", "info"}, vuln["id"]
        assert vuln["cwes"], vuln["id"]
