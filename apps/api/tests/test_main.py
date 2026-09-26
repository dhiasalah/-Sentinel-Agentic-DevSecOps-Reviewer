from fastapi.testclient import TestClient

from app.main import app
import redis

from app import main

client = TestClient(app)

def test_root_returns_message():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Sentinel API is running"}


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_ready_returns_503_when_redis_is_down(monkeypatch):
    def fake_ping():
        raise redis.ConnectionError("down")

    monkeypatch.setattr(main.redis_client, "ping", fake_ping)

    response = client.get("/ready")
    assert response.status_code == 503
