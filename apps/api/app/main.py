import hashlib
import json
import logging
from typing import Annotated

import redis
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.webhooks import verify_signature

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel.webhooks")
PR_ACTIONS = {"opened", "synchronize", "reopened"}
QUEUE = "sentinel:jobs"
SEEN_TTL_SECONDS = 24 * 3600

app = FastAPI(title="Sentinel API")
redis_client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)

@app.get("/")
def root():
    return {"message": "Sentinel API is running"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    try:
        redis_client.ping()
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="redis unavailable")
    return {"status": "ready"}

@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
    x_github_delivery: Annotated[str | None, Header()] = None,
):
    body = await request.body()
    if not verify_signature(settings.github_webhook_secret.get_secret_value(), body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="invalid signature")

    if x_github_event == "ping":
        return {"status": "pong"}

    payload = json.loads(body)
    if x_github_event != "pull_request" or payload.get("action") not in PR_ACTIONS:
        return {"status": "ignored"}

    pr = payload["pull_request"]
    job = {
        "delivery": x_github_delivery,
        "repo": payload["repository"]["full_name"],
        "pr": pr["number"],
        "head_sha": pr["head"]["sha"],
        "installation_id": payload["installation"]["id"],
    }
    seen_key = "sentinel:seen:" + hashlib.sha256(body).hexdigest()
    try:
        if not redis_client.set(seen_key, 1, nx=True, ex=SEEN_TTL_SECONDS):
            logger.info("duplicate delivery %s ignored", x_github_delivery)
            return {"status": "duplicate"}
        redis_client.lpush(QUEUE, json.dumps(job))
    except redis.RedisError:
        logger.exception("could not enqueue delivery %s", x_github_delivery)
        raise HTTPException(status_code=503, detail="queue unavailable")

    logger.info("queued pull_request %s", job)

    return JSONResponse(status_code=202, content={"status": "accepted", "pr": job["pr"]})
