import pytest

from sentinel import approvals, fix_graph
from sentinel.approvals import apply_approvals, fix_record
from sentinel.fix_graph import build_fix_graph, open_checkpoints, patch_id
from sentinel.fixer import Patch
from sentinel.models import Finding, TriagedIssue
from sentinel.sandbox import Verification

FINDING = Finding(tool="semgrep", rule_id="yaml-load", severity="ERROR", message="m", file="app.py", line=5)
ISSUE = TriagedIssue(title="Unsafe YAML", severity="high", false_positive=False, explanation="e", fix="f",
                     findings=[FINDING])
PATCH = Patch(summary="use safe_load", diff="--- a/app.py\n+++ b/app.py\n", provider="fake")
TARGET = {"repo": "o/r", "pr": 7, "head_sha": "a" * 40, "fix_id": "fix-0000aaaa"}
USER = "b734c29e-2684-435a-b0b3-195147dd7708"


class FakeStore:
    def __init__(self, approvals):
        self.approvals, self.updates = approvals, []

    def pending_approvals(self):
        return self.approvals

    def user_login(self, user_id):
        assert user_id == USER
        return "dhiasalah"

    def update_fix(self, fix_id, fields):
        self.updates.append((fix_id, fields))


@pytest.fixture
def paused(tmp_path, monkeypatch):
    monkeypatch.setattr(fix_graph, "propose_fix", lambda *a: PATCH)
    monkeypatch.setattr(fix_graph, "verify_fix", lambda *a: Verification(changed=["app.py"], scanners=["semgrep"]))
    monkeypatch.setattr(fix_graph, "open_fix_pr", lambda *a: "https://github.com/o/r/pull/8")
    approvals._reported.clear()
    db = tmp_path / "a.sqlite"
    with open_checkpoints(db) as saver:
        build_fix_graph(None, saver).invoke({"path": ".", "issue": ISSUE, "all_findings": [FINDING], "target": TARGET},
                                            {"configurable": {"thread_id": "fix-0000aaaa"}})
    return db


def approval(decision="approve", pid=None, fix_id="fix-0000aaaa"):
    return {"fix_id": fix_id, "decision": decision, "patch_id": pid or patch_id(PATCH.diff), "reason": "", "decided_by": USER}


def test_a_dashboard_approval_resumes_the_fix_and_records_the_pr(paused):
    store = FakeStore([approval()])
    assert apply_approvals(store, paused, None) == 1
    assert store.updates == [("fix-0000aaaa", {"status": "approved", "pr_url": "https://github.com/o/r/pull/8"})]


def test_a_dashboard_rejection_is_recorded(paused):
    store = FakeStore([approval("reject")])
    apply_approvals(store, paused, None)
    assert store.updates == [("fix-0000aaaa", {"status": "rejected", "pr_url": None})]


def test_an_approval_for_another_patch_is_a_rejection(paused):
    store = FakeStore([approval(pid="0123456789ab")])
    apply_approvals(store, paused, None)
    assert store.updates == [("fix-0000aaaa", {"status": "rejected", "pr_url": None})]


def test_a_fix_this_machine_never_paused_is_left_waiting(paused):
    store = FakeStore([approval(fix_id="fix-ffffffff")])
    assert apply_approvals(store, paused, None) == 0
    assert store.updates == []


def test_the_dashboard_row_carries_what_the_human_saw():
    pending = {"patch_id": "03cf51fe1631", "summary": "s", "provider": "groq", "diff": "d", "scanners": ["semgrep"]}
    row = fix_record("fix-0000aaaa", 1, ISSUE, TARGET, pending)
    assert row == {"id": "fix-0000aaaa", "repo_id": 1, "pr": 7, "head_sha": "a" * 40, "issue_title": "Unsafe YAML",
                   "summary": "s", "provider": "groq", "diff": "d", "patch_id": "03cf51fe1631",
                   "scanners": ["semgrep"], "status": "waiting"}
