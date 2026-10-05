import logging
import uuid
from pathlib import Path

from langgraph.types import Command

from sentinel.config import Settings
from sentinel.fix_graph import Decision, build_fix_graph, open_checkpoints
from sentinel.models import TriagedIssue
from sentinel.store import Store

log = logging.getLogger(__name__)

DECIDED = {"approved", "rejected", "outdated"}
_reported: set[str] = set()


def fix_record(fix_id: str, repo_id: int, issue: TriagedIssue, target: dict, pending: dict) -> dict:
    """The row the dashboard shows for a fix waiting for a human (pending = the interrupt payload)."""
    return {
        "id": fix_id,
        "repo_id": repo_id,
        "pr": target["pr"],
        "head_sha": target["head_sha"],
        "issue_title": issue.title,
        "summary": pending["summary"],
        "provider": pending["provider"],
        "diff": pending["diff"],
        "patch_id": pending["patch_id"],
        "scanners": pending["scanners"],
        "status": "waiting",
    }


def apply_approvals(store: Store, db: Path, settings: Settings | None) -> int:
    """Resume every paused fix that got a decision in the dashboard, then record the outcome."""
    applied = 0
    for approval in store.pending_approvals():
        fix_id = approval["fix_id"]
        config = {"configurable": {"thread_id": fix_id}}
        with open_checkpoints(db) as saver:
            graph = build_fix_graph(None, saver, settings)
            state = graph.get_state(config)
            if state.interrupts:
                login = store.user_login(str(uuid.UUID(approval["decided_by"])))
                decision = Decision(decision=approval["decision"], patch_id=approval["patch_id"],
                                    by=login, reason=approval["reason"])
                log.info("fix %s: %s by %s (dashboard)", fix_id, approval["decision"], login)
                graph.invoke(Command(resume=decision.model_dump()), config)
                state = graph.get_state(config)
        status = state.values.get("status")
        if state.next or status not in DECIDED:
            if fix_id not in _reported:
                log.warning("fix %s: decided in the dashboard but its run can't finish here (status %s, next %s)",
                            fix_id, status, state.next)
                _reported.add(fix_id)
            continue
        store.update_fix(fix_id, {"status": status, "pr_url": state.values.get("pr_url")})
        applied += 1
    return applied
