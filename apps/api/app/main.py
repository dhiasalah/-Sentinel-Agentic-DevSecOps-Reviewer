import redis
from fastapi import FastAPI, HTTPException
from app.config import settings

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
