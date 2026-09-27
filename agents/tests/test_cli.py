import json

from sentinel.cli import EXIT_ISSUES, EXIT_OK, exit_code, parse_args, render_json, render_text
from sentinel.models import Finding, TriagedIssue


def make_issue(severity="high", reasons=None):
    finding = Finding(tool="semgrep", rule_id="r", severity="ERROR", message="m", file="app.py", line=24)
    return TriagedIssue(title="Command injection", severity=severity, false_positive=False,
                        explanation="e", fix="f", findings=[finding, finding], review_reasons=reasons or [])


def test_fails_when_an_issue_reaches_the_threshold():
    assert exit_code([make_issue("high")], fail_on="high") == EXIT_ISSUES


def test_passes_when_issues_are_below_the_threshold():
    assert exit_code([make_issue("medium")], fail_on="high") == EXIT_OK


def test_no_issues_passes():
    assert exit_code([], fail_on="info") == EXIT_OK


def test_text_report_shows_location_once_and_review_flags():
    text = render_text([make_issue(reasons=["possible prompt injection"])], finding_count=2)
    assert text.count("app.py:24") == 1
    assert "needs human review: possible prompt injection" in text
    assert "2 scanner findings -> 1 issues" in text


def test_json_report_is_valid_json():
    data = json.loads(render_json([make_issue()]))
    assert data[0]["severity"] == "high"
    assert data[0]["findings"][0]["line"] == 24


def test_default_fail_on_is_high():
    assert parse_args(["scan", "some/folder"]).fail_on == "high"
