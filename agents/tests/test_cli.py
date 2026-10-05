import json

import pytest

from sentinel import cli
from sentinel.cli import EXIT_ERROR, EXIT_ISSUES, EXIT_OK, exit_code, parse_args, render_json, render_text
from sentinel.models import Finding, ScannerFailure, TriagedIssue
from sentinel.fixer import Patch
from sentinel.sandbox import SandboxError, Verification



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
    
def test_incomplete_scan_never_passes(monkeypatch, capsys):
    failure = ScannerFailure(scanner="semgrep", error="TimeoutExpired")

    class FakeGraph:
        def invoke(self, state):
            return {"findings": [], "issues": [], "failures": [failure]}

    monkeypatch.setattr(cli, "Settings", lambda: None)
    monkeypatch.setattr(cli, "build_router", lambda settings: None)
    monkeypatch.setattr(cli, "build_graph", lambda router: FakeGraph())
    assert cli.main(["scan", "."]) == EXIT_ERROR
    assert "scanner semgrep failed (TimeoutExpired)" in capsys.readouterr().err

def test_fix_prints_only_the_diff_on_stdout(monkeypatch, capsys, tmp_path):
    report = tmp_path / "report.json"
    report.write_text(render_json([make_issue()]), encoding="utf-8")
    seen = {}

    def fake_fix(issue, root, router, all_findings):
        seen["title"] = issue.title
        return Patch(summary="use a list", diff="--- a/app.py\n", provider="fake")

    monkeypatch.setattr(cli, "Settings", lambda: None)
    monkeypatch.setattr(cli, "build_router", lambda settings: None)
    monkeypatch.setattr(cli, "propose_fix", fake_fix)
    patch = tmp_path / "fix.patch"
    assert cli.main(["fix", ".", "--report", str(report), "--issue", "1", "-o", str(patch)]) == EXIT_OK
    assert patch.read_bytes() == b"--- a/app.py\n"
    out = capsys.readouterr()
    assert out.out == "--- a/app.py\n"
    assert "use a list (by fake)" in out.err
    assert seen["title"] == "Command injection"
    assert cli.main(["fix", ".", "--report", str(report), "--issue", "2"]) == EXIT_ERROR


def test_verify_exit_code_follows_the_sandbox_verdict(monkeypatch, capsys, tmp_path):
    report = tmp_path / "report.json"
    report.write_text(render_json([make_issue()]), encoding="utf-8")
    patch = tmp_path / "fix.patch"
    patch.write_text("--- a/app.py\n", encoding="utf-8")
    verdicts = [Verification(changed=["app.py"], scanners=["semgrep"]),
                Verification(changed=["app.py"], scanners=["semgrep"], problems=["app.py no longer parses"])]

    def fake_verify(root, diff, issue, all_findings, scanners):
        if not verdicts:
            raise SandboxError("patch does not apply")
        return verdicts.pop(0)

    monkeypatch.setattr(cli, "verify_fix", fake_verify)
    args = ["verify", ".", "--report", str(report), "--issue", "1", "--patch", str(patch)]
    assert cli.main(args) == EXIT_OK
    assert "verified: the issue is gone" in capsys.readouterr().out
    assert cli.main(args) == EXIT_ISSUES
    assert "problem: app.py no longer parses" in capsys.readouterr().out
    assert cli.main(args) == EXIT_ISSUES
    assert "patch rejected: patch does not apply" in capsys.readouterr().err


def test_propose_then_approve_from_another_command(monkeypatch, capsys, tmp_path):
    from sentinel import fix_graph

    report = tmp_path / "report.json"
    report.write_text(render_json([make_issue()]), encoding="utf-8")
    monkeypatch.setattr(cli, "Settings", lambda: None)
    monkeypatch.setattr(cli, "build_router", lambda settings: None)
    monkeypatch.setattr(fix_graph, "propose_fix", lambda *args: Patch(summary="s", diff="-a\n+b\n", provider="fake"))
    monkeypatch.setattr(fix_graph, "verify_fix", lambda *args: Verification(changed=["app.py"], scanners=["semgrep"]))
    db = ["--db", str(tmp_path / "approvals.sqlite")]

    assert cli.main(["propose", ".", "--report", str(report), "--issue", "1", *db]) == EXIT_OK
    out = capsys.readouterr()
    assert out.out == "-a\n+b\n"
    fix_id, pid = out.err.split("fix ")[1].split()[0], out.err.split("Patch id: ")[1].split()[0]
    assert cli.main(["review", fix_id, "--approve", pid, *db]) == EXIT_OK
    assert f"fix {fix_id} approved by " in capsys.readouterr().err
    assert cli.main(["review", fix_id, "--reject", *db]) == EXIT_OK
    assert "not waiting for a decision" in capsys.readouterr().err
    assert cli.main(["review", "fix-unknown", *db]) == EXIT_ERROR


@pytest.mark.parametrize("argv", [["propose"], ["propose", ".", "--pr", "o/r#1"]])
def test_propose_needs_a_folder_or_a_pr(argv):
    with pytest.raises(SystemExit):
        parse_args([*argv, "--report", "r.json", "--issue", "1"])
