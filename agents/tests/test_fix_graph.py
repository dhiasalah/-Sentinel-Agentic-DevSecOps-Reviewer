import pytest
from langgraph.types import Command

from sentinel import fix_graph
from sentinel.fix_graph import build_fix_graph, open_checkpoints, patch_id
from sentinel.fixer import NotFixable, Patch
from sentinel.models import Finding, TriagedIssue
from sentinel.sandbox import Verification

FINDING = Finding(tool="semgrep", rule_id="yaml-load", severity="ERROR", message="m", file="app.py", line=5)
ISSUE = TriagedIssue(title="Unsafe YAML", severity="high", false_positive=False, explanation="e", fix="f",
                     findings=[FINDING])
PATCH = Patch(summary="use safe_load", diff="--- a/app.py\n+++ b/app.py\n", provider="fake")
START = {"path": ".", "issue": ISSUE, "all_findings": [FINDING]}
CONFIG = {"configurable": {"thread_id": "fix-test"}}


@pytest.fixture
def fakes(monkeypatch):
    calls = {"fix": 0, "verify": 0}

    def fake_fix(issue, root, router, all_findings):
        calls["fix"] += 1
        return PATCH

    def fake_verify(root, diff, issue, all_findings, scanners):
        calls["verify"] += 1
        return Verification(changed=["app.py"], scanners=["gitleaks", "semgrep"])

    monkeypatch.setattr(fix_graph, "propose_fix", fake_fix)
    monkeypatch.setattr(fix_graph, "verify_fix", fake_verify)
    return calls


def decide(db, decision, pid, reason=""):
    with open_checkpoints(db) as saver:
        graph = build_fix_graph(None, saver)
        graph.invoke(Command(resume={"decision": decision, "patch_id": pid, "by": "alice", "reason": reason}), CONFIG)
        return graph.get_state(CONFIG).values


def start(db):
    with open_checkpoints(db) as saver:
        graph = build_fix_graph(None, saver)
        graph.invoke(START, CONFIG)
        return graph.get_state(CONFIG)


def test_a_verified_patch_waits_for_a_human_and_survives_a_restart(tmp_path, fakes):
    state = start(tmp_path / "a.sqlite")
    pending = state.interrupts[0].value
    assert state.next == ("approval",)
    assert pending["diff"] == PATCH.diff and pending["patch_id"] == patch_id(PATCH.diff)
    values = decide(tmp_path / "a.sqlite", "approve", pending["patch_id"])
    assert (values["status"], values["decided_by"]) == ("approved", "alice")
    assert isinstance(values["issue"], TriagedIssue) and isinstance(values["verification"], Verification)
    assert fakes == {"fix": 1, "verify": 1}


def test_approving_a_different_patch_is_a_rejection(tmp_path, fakes):
    start(tmp_path / "a.sqlite")
    values = decide(tmp_path / "a.sqlite", "approve", "0123456789ab")
    assert values["status"] == "rejected" and "not " + patch_id(PATCH.diff) in values["reason"]


def test_a_rejection_keeps_the_reason(tmp_path, fakes):
    start(tmp_path / "a.sqlite")
    values = decide(tmp_path / "a.sqlite", "reject", patch_id(PATCH.diff), "breaks the config loader")
    assert (values["status"], values["reason"]) == ("rejected", "breaks the config loader")


def test_an_unclear_answer_is_a_no(tmp_path, fakes):
    start(tmp_path / "a.sqlite")
    values = decide(tmp_path / "a.sqlite", "yes please", patch_id(PATCH.diff))
    assert (values["status"], values["reason"]) == ("rejected", "the decision was malformed")


def test_no_human_is_asked_when_the_sandbox_says_no(tmp_path, fakes, monkeypatch):
    bad = Verification(changed=["app.py"], scanners=["semgrep"], still_there=[FINDING])
    monkeypatch.setattr(fix_graph, "verify_fix", lambda *args: bad)
    state = start(tmp_path / "a.sqlite")
    assert not state.interrupts and state.values["status"] == "not_verified"


def test_a_refused_issue_never_reaches_the_sandbox(tmp_path, fakes, monkeypatch):
    def refuse(*args):
        raise NotFixable("leaked secrets must be rotated by a human")

    monkeypatch.setattr(fix_graph, "propose_fix", refuse)
    state = start(tmp_path / "a.sqlite")
    assert state.values["status"] == "refused" and fakes["verify"] == 0


TARGET = {"repo": "o/r", "pr": 7, "head_sha": "a" * 40, "fix_id": "fix-test"}


def start_on_github(db):
    with open_checkpoints(db) as saver:
        build_fix_graph(None, saver).invoke({**START, "target": TARGET}, CONFIG)


def test_an_approved_github_fix_opens_a_pr(tmp_path, fakes, monkeypatch):
    opened = []
    monkeypatch.setattr(fix_graph, "open_fix_pr", lambda *args: opened.append(args) or "https://github.com/o/r/pull/8")
    start_on_github(tmp_path / "a.sqlite")
    values = decide(tmp_path / "a.sqlite", "approve", patch_id(PATCH.diff))
    assert (values["status"], values["pr_url"]) == ("approved", "https://github.com/o/r/pull/8")
    assert opened[0][:5] == ("o/r", 7, "a" * 40, PATCH.diff, "fix-test") and opened[0][7] == "alice"


@pytest.mark.parametrize("github, decision", [(False, "approve"), (True, "reject")])
def test_no_pr_for_a_local_or_rejected_fix(tmp_path, fakes, monkeypatch, github, decision):
    monkeypatch.setattr(fix_graph, "open_fix_pr", lambda *args: pytest.fail("must not open a PR"))
    start_on_github(tmp_path / "a.sqlite") if github else start(tmp_path / "a.sqlite")
    values = decide(tmp_path / "a.sqlite", decision, patch_id(PATCH.diff))
    assert "pr_url" not in values


def test_a_pr_that_moved_after_approval_is_outdated(tmp_path, fakes, monkeypatch):
    def moved(*args):
        raise fix_graph.PRMoved("o/r#7 moved from aaaaaaa to bbbbbbb: run propose again")

    monkeypatch.setattr(fix_graph, "open_fix_pr", moved)
    start_on_github(tmp_path / "a.sqlite")
    values = decide(tmp_path / "a.sqlite", "approve", patch_id(PATCH.diff))
    assert values["status"] == "outdated" and "moved from" in values["reason"]
