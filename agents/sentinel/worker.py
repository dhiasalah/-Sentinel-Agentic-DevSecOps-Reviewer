import logging
import sys

import redis
from pydantic import BaseModel

from sentinel.cli import render_text
from sentinel.config import Settings
from sentinel.github.comment import post_report
from sentinel.github.scan_pr import scan_pr
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


def start_scan_record(store: Store | None, job: Job) -> int | None:
    if store is None:
        return None
    repo_id = best_effort("look up the repo", store.repo_id, job.repo)
    if repo_id is None:
        logger.info("%s is not linked to a dashboard user, results are not stored", job.repo)
        return None
    return best_effort("record the scan", store.start_scan, repo_id, job.pr, job.head_sha)


def process_one(r: redis.Redis, settings: Settings, timeout: int = 5) -> bool:
    raw = r.blmove(QUEUE, PROCESSING, timeout, src="RIGHT", dest="LEFT")
    if raw is None:
        return False
    try:
        job = Job.model_validate_json(raw)
        logger.info("scanning %s#%d @ %s (delivery %s)", job.repo, job.pr, job.head_sha[:7], job.delivery)
        store = open_store(settings)
        scan_id = start_scan_record(store, job)
        try:
            issues, failures = scan_pr(job.repo, job.head_sha, job.installation_id, settings)
        except Exception:
            if scan_id:
                best_effort("mark the scan failed", store.fail_scan, scan_id)
            raise
        if scan_id:
            best_effort("store the results", store.finish_scan, scan_id, issues, failures)
        finding_count = sum(len(i.findings) for i in issues)
        logger.info("%s#%d done, %d issue(s)\n%s", job.repo, job.pr, len(issues), render_text(issues, finding_count))
        for failure in failures:
            logger.warning("%s#%d scanner %s failed (%s)", job.repo, job.pr, failure.scanner, failure.error)
        action = post_report(job.repo, job.pr, job.head_sha, job.installation_id, issues, finding_count, failures,
                             settings)
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
    logger.info("worker ready, waiting for jobs on %s", QUEUE)
    while True:
        process_one(r, settings)


if __name__ == "__main__":
    main()
