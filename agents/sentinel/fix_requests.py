import logging
import secrets
from pathlib import Path

from sentinel.approvals import fix_record
from sentinel.config import Settings
from sentinel.fix_graph import build_fix_graph, open_checkpoints
from sentinel.github.fix_pr import checkout_commit
from sentinel.llm.providers import ProviderUnavailable
from sentinel.llm.router import AllProvidersFailed, build_router
from sentinel.models import Finding, RepoSettings, TriagedIssue
from sentinel.store import Store

log = logging.getLogger(__name__)

ENDED = {"refused", "no_fix", "not_verified"}
# Fixed words only: the dashboard turns each into a sentence. Nothing a model or a repository wrote is stored.
REASONS = {"secret", "false_positive", "prompt_injection", "too_large", "not_a_file", "model_declined",
           "patch_rejected", "new_findings", "still_reported", "broken_patch", "ai_unavailable", "ai_bad_answer"}


def failure_reason(e: Exception) -> str:
    if isinstance(e, AllProvidersFailed):
        busy = e.errors and all(isinstance(x, ProviderUnavailable) for x in e.errors)
        return "ai_unavailable" if busy else "ai_bad_answer"
    return "error"


ISSUE_FIELDS = ("title", "severity", "false_positive", "explanation", "fix", "review_reasons", "findings")


def propose(request: dict, store: Store, db: Path, settings: Settings) -> tuple[str, str | None, str | None]:
    """Run the fix graph on the scanned commit. Returns the request's new status, the fix id if one is waiting,
    and a reason code when it ended without one."""
    row = request["issue"]
    scan = row["scan"]
    issue = TriagedIssue.model_validate({k: row[k] for k in ISSUE_FIELDS})
    all_findings = [Finding.model_validate(f) for f in store.scan_findings(scan["id"])]
    try:
        order = store.repo_settings(scan["repo_id"]).llm_order
    except Exception:
        log.warning("fix request %s: could not read the repo settings, using the default AI order", request["id"])
        order = RepoSettings().llm_order

    fix_id = f"fix-{secrets.token_hex(4)}"
    target = {"repo": scan["repo"]["full_name"], "pr": scan["pr"], "head_sha": scan["head_sha"], "fix_id": fix_id}
    config = {"configurable": {"thread_id": fix_id}}
    with open_checkpoints(db) as saver, checkout_commit(target["repo"], target["head_sha"], settings) as path:
        graph = build_fix_graph(build_router(settings, order), saver, settings)
        graph.invoke({"path": str(path), "issue": issue, "all_findings": all_findings, "target": target}, config)
        state = graph.get_state(config)

    if state.interrupts:
        store.save_fix(fix_record(fix_id, scan["repo_id"], issue, target, state.interrupts[0].value))
        return "waiting", fix_id, None
    status, code = state.values.get("status"), state.values.get("reason_code")
    log.info("fix request %s: ended as %s (%s)", request["id"], status, state.values.get("reason", ""))
    if status not in ENDED:
        return "failed", None, "error"
    return status, None, code if code in REASONS else "other"


def run_fix_request(store: Store, db: Path, settings: Settings) -> bool:
    """Take the oldest fix asked for in the dashboard and turn it into a fix waiting for a human."""
    request = store.next_fix_request()
    if request is None or not store.claim_fix_request(request["id"]):
        return False
    log.info("fix request %s: %s", request["id"], request["issue"]["title"][:80])
    try:
        status, fix_id, reason = propose(request, store, db, settings)
    except Exception as e:
        log.exception("fix request %s failed", request["id"])
        status, fix_id, reason = "failed", None, failure_reason(e)
    store.finish_fix_request(request["id"], status, fix_id, reason)
    log.info("fix request %s: %s%s", request["id"], status, f" ({fix_id})" if fix_id else f" ({reason})")
    return True
