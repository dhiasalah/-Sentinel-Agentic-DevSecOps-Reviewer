import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field, ValidationError

from sentinel.config import Settings
from sentinel.fixer import NotFixable, Patch, propose_fix
from sentinel.github.fix_pr import PRMoved, open_fix_pr
from sentinel.graph import SCANNERS
from sentinel.llm.router import LLMRouter
from sentinel.models import Finding, TriagedIssue
from sentinel.sandbox import SandboxError, Verification, verify_fix

ALLOWED_TYPES = [
    ("sentinel.models", "Finding"), ("sentinel.models", "TriagedIssue"),
    ("sentinel.fixer", "Patch"), ("sentinel.sandbox", "Verification"),
]


class FixState(TypedDict, total=False):
    path: str
    issue: TriagedIssue
    all_findings: list[Finding]
    patch: Patch
    verification: Verification
    status: str
    reason: str
    reason_code: str
    decided_by: str
    decided_at: str
    target: dict | None
    pr_url: str


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    patch_id: str = Field(max_length=64)
    by: str = Field(min_length=1, max_length=100)
    reason: str = Field(default="", max_length=500)


def patch_id(diff: str) -> str:
    return hashlib.sha256(diff.encode("utf-8")).hexdigest()[:12]


@contextmanager
def open_checkpoints(db: Path) -> Iterator[SqliteSaver]:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, check_same_thread=False)
    try:
        yield SqliteSaver(conn, serde=JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_TYPES))
    finally:
        conn.close()
def stop_or(next_node: str):
    return lambda state: END if state.get("status") else next_node


def after_approval(state: FixState) -> str:
    return "open_pr" if state["status"] == "approved" and state.get("target") else END


def build_fix_graph(router: LLMRouter, checkpointer: SqliteSaver, settings: Settings | None = None):
    def fix(state: FixState) -> dict:
        try:
            patch = propose_fix(state["issue"], Path(state["path"]), router, state["all_findings"])
        except NotFixable as e:
            return {"status": "refused", "reason": str(e), "reason_code": e.code}
        if not patch.diff:
            return {"patch": patch, "status": "no_fix", "reason": patch.summary, "reason_code": "model_declined"}
        return {"patch": patch}

    def verify(state: FixState) -> dict:
        try:
            result = verify_fix(Path(state["path"]), state["patch"].diff, state["issue"],
                                state["all_findings"], SCANNERS)
        except SandboxError as e:
            return {"status": "not_verified", "reason": str(e), "reason_code": "patch_rejected"}
        if not result.verified:
            code = "new_findings" if result.new else "still_reported" if result.still_there else "broken_patch"
            return {"verification": result, "status": "not_verified", "reason": "the sandbox did not verify the patch",
                    "reason_code": code}
        return {"verification": result}

    def approval(state: FixState) -> dict:
        expected = patch_id(state["patch"].diff)
        raw = interrupt({
            "patch_id": expected,
            "summary": state["patch"].summary,
            "provider": state["patch"].provider,
            "diff": state["patch"].diff,
            "scanners": state["verification"].scanners,
        })
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            answer = Decision.model_validate(raw)
        except ValidationError:
            return {"status": "rejected", "reason": "the decision was malformed", "decided_at": now}
        decided = {"decided_by": answer.by, "decided_at": now}
        if answer.patch_id != expected:
            return {**decided, "status": "rejected",
                    "reason": f"the approval was for patch {answer.patch_id}, not {expected}"}
        if answer.decision == "approve":
            return {**decided, "status": "approved"}
        return {**decided, "status": "rejected", "reason": answer.reason or "rejected by a human"}

    def open_pr(state: FixState) -> dict:
        target, patch = state["target"], state["patch"]
        try:
            url = open_fix_pr(target["repo"], target["pr"], target["head_sha"], patch.diff, target["fix_id"],
                              patch.summary, patch_id(patch.diff), state["decided_by"], settings)
        except PRMoved as e:
            return {"status": "outdated", "reason": str(e)}
        return {"pr_url": url}

    graph = StateGraph(FixState)
    graph.add_node("fix", fix)
    graph.add_node("verify", verify)
    graph.add_node("approval", approval)
    graph.add_node("open_pr", open_pr)
    graph.add_edge(START, "fix")
    graph.add_conditional_edges("fix", stop_or("verify"), ["verify", END])
    graph.add_conditional_edges("verify", stop_or("approval"), ["approval", END])
    graph.add_conditional_edges("approval", after_approval, ["open_pr", END])
    graph.add_edge("open_pr", END)
    return graph.compile(checkpointer=checkpointer)
