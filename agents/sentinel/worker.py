import logging
import sys

import redis
from pydantic import BaseModel

from sentinel.approvals import apply_approvals
from sentinel.cli import DEFAULT_DB, render_text
from sentinel.config import Settings
from sentinel.fix_requests import run_fix_request
from sentinel.github.comment import post_report
from sentinel.github.scan_pr import scan_pr
from sentinel.models import RepoSettings, ScanEvent, TriagedIssue
from sentinel.policy import rank
from sentinel.store import Store, open_store

logger = logging.getLogger(__name__)

QUEUE = "sentinel:jobs"
PROCESSING = "sentinel:jobs:processing"
DEAD = "sentinel:jobs:dead"


class Job(BaseModel):
    delivery: str | None = None
    repo: str
    pr: int
    head_sha: str
    installation_id: int


def best_effort(what: str, fn, *args):
    try:
        return fn(*args)
    except Exception:
        logger.warning("dashboard: could not %s", what, exc_info=True)
        return None


def link_scan(store: Store | None, job: Job) -> tuple[int | None, RepoSettings]:
    """Find the dashboard repo, record the scan, read the owner's settings. Every step may fail without harm."""
    if store is None:
        return None, RepoSettings()
    repo_id = best_effort("look up the repo", store.repo_id, job.repo)
    if repo_id is None:
        logger.info("%s is not linked to a dashboard user, results are not stored", job.repo)
        return None, RepoSettings()
    # Unreadable settings fall back to the defaults, which scan everything: failing toward *more* checks.
    repo_settings = best_effort("read the repo settings", store.repo_settings, repo_id) or RepoSettings()
    return best_effort("record the scan", store.start_scan, repo_id, job.pr, job.head_sha), repo_settings


def split_by_threshold(issues: list[TriagedIssue], minimum: str) -> tuple[list[TriagedIssue], int]:
    """Issues shown in the PR comment, and how many were hidden. The dashboard always keeps all of them."""
    shown = [issue for issue in issues if rank(issue.severity) <= rank(minimum)]
    return shown, len(issues) - len(shown)


def process_one(r: redis.Redis, settings: Settings, timeout: int = 5) -> bool:
    raw = r.blmove(QUEUE, PROCESSING, timeout, src="RIGHT", dest="LEFT")
    if raw is None:
        return False
    try:
        job = Job.model_validate_json(raw)
        logger.info("scanning %s#%d @ %s (delivery %s)", job.repo, job.pr, job.head_sha[:7], job.delivery)
        store = open_store(settings)
        scan_id, repo_settings = link_scan(store, job)

        def progress(event: ScanEvent) -> None:
            if scan_id:
                best_effort("record progress", store.add_event, scan_id, event)

        try:
            issues, failures = scan_pr(job.repo, job.head_sha, job.installation_id, settings,
                                       repo_settings=repo_settings, on_event=progress)
        except Exception:
            if scan_id:
                best_effort("mark the scan failed", store.fail_scan, scan_id)
            raise
        finding_count = sum(len(i.findings) for i in issues)
        logger.info("%s#%d done, %d issue(s)\n%s", job.repo, job.pr, len(issues), render_text(issues, finding_count))
        for failure in failures:
            logger.warning("%s#%d scanner %s failed (%s)", job.repo, job.pr, failure.scanner, failure.error)
        shown, hidden = split_by_threshold(issues, repo_settings.report_min_severity)
        progress(ScanEvent(stage="report", status="started", count=len(shown)))
        try:
            action = post_report(job.repo, job.pr, job.head_sha, job.installation_id, shown, finding_count, failures,
                                 settings, hidden)
            progress(ScanEvent(stage="report", status="ok", count=len(shown)))
        except Exception:
            progress(ScanEvent(stage="report", status="failed"))
            raise
        finally:
            # Stored even if the comment failed, and last: the live view stops once the status leaves "running".
            if scan_id:
                best_effort("store the results", store.finish_scan, scan_id, issues, failures)
        logger.info("%s#%d report comment %s", job.repo, job.pr, action)

    except Exception:
        logger.exception("job failed, moved to %s", DEAD)
        r.lpush(DEAD, raw)
    finally:
        r.lrem(PROCESSING, 1, raw)
    return True


def requeue_stale(r: redis.Redis) -> int:
    moved = 0
    while r.lmove(PROCESSING, QUEUE, src="RIGHT", dest="RIGHT") is not None:
        moved += 1
    return moved


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.stderr.reconfigure(encoding="utf-8")
    settings = Settings()
    r = redis.Redis.from_url(settings.redis_url, socket_timeout=30)
    r.ping()
    if moved := requeue_stale(r):
        logger.warning("requeued %d unfinished job(s) from a previous run", moved)
    store = open_store(settings)
    if store and (moved := best_effort("requeue unfinished fix requests", store.requeue_working_fix_requests)):
        logger.warning("requeued %d unfinished fix request(s) from a previous run", moved)
    logger.info("worker ready, waiting for jobs on %s%s", QUEUE, ", dashboard decisions and fix requests" if store else "")
    while True:
        process_one(r, settings)
        if store:
            best_effort("apply dashboard decisions", apply_approvals, store, DEFAULT_DB, settings)
            # One fix per loop: a scan waiting in the queue never sits behind a long line of fixes.
            best_effort("run a requested fix", run_fix_request, store, DEFAULT_DB, settings)


if __name__ == "__main__":
    main()
