import json

import pytest

from sentinel.llm.router import LLMResponse
from sentinel.models import Finding
from sentinel.triage import TriageError, build_prompt, parse_response, read_snippet, triage


def make_finding(line=2, rule="sqli", severity="ERROR"):
    return Finding(tool="semgrep", rule_id=rule, severity=severity, message="msg", file="app.py", line=line)


def issue(ids, severity="high"):
    return {"finding_ids": ids, "title": "t", "severity": severity,
            "false_positive": False, "explanation": "e", "fix": "f"}


def answer(*issues):
    return json.dumps({"issues": list(issues)})


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "app.py").write_text("a = 1\nquery = f'SELECT {x}'\nb = 2\n")
    return tmp_path


class FakeRouter:
    def __init__(self, text):
        self.text = text
        self.json_mode = None

    def complete(self, system, user, json_mode=False):
        self.json_mode = json_mode
        return LLMResponse(provider="fake", text=self.text)


def test_merges_duplicate_findings_into_one_issue():
    findings = [make_finding(rule="sqli-a"), make_finding(rule="sqli-b")]
    issues = parse_response(answer(issue([1, 2])), findings)
    assert len(issues) == 1
    assert issues[0].findings == findings


def test_rejects_invented_finding_id():
    with pytest.raises(TriageError, match="unknown"):
        parse_response(answer(issue([1, 99])), [make_finding()])


def test_rejects_dropped_finding():
    with pytest.raises(TriageError, match="dropped"):
        parse_response(answer(issue([1])), [make_finding(), make_finding()])


def test_rejects_prose_instead_of_json():
    with pytest.raises(TriageError):
        parse_response("Sure! Here is the triage you asked for.", [make_finding()])


def test_snippet_refuses_paths_outside_repo(repo):
    with pytest.raises(ValueError):
        read_snippet(repo, "../outside.txt", 1)


def test_code_is_wrapped_as_untrusted(repo):
    prompt = build_prompt([make_finding()], repo, tag="abc123")
    inside = prompt.split("<untrusted-abc123>")[1].split("</untrusted-abc123>")[0]
    assert "SELECT" in inside
    assert "app.py:2" in inside


def test_triage_asks_for_json_and_sorts_by_severity(repo):
    router = FakeRouter(answer(issue([1], "low"), issue([2], "critical")))
    issues = triage([make_finding(1, severity="INFO"), make_finding(3)], repo, router)
    assert router.json_mode is True
    assert [i.severity for i in issues] == ["critical", "low"]

def test_hijacked_llm_cannot_hide_a_real_finding(repo):
    hijacked = answer({**issue([1], severity="info"), "false_positive": True})
    issues = triage([make_finding(line=2)], repo, FakeRouter(hijacked))
    assert issues[0].severity == "high"
    assert issues[0].review_reasons

def test_secret_lines_never_reach_the_llm(tmp_path):
    (tmp_path / "app.py").write_text('a = 1\nTOKEN = "hunter2hunter2"\nquery = f"SELECT {x}"\n')
    leak = Finding(tool="gitleaks", rule_id="secret", severity="ERROR", message="m",
                   file="app.py", line=2, end_line=2)
    prompt = build_prompt([leak, make_finding(line=3)], tmp_path, tag="abc123")
    assert "hunter2" not in prompt
    assert "SELECT" in prompt
