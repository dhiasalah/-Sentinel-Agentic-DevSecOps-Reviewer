import os

import redis
from fastapi import FastAPI, HTTPException

app = FastAPI(title="Sentinel API")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=2)

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
