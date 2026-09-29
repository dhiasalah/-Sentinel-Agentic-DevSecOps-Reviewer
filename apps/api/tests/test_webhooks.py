import hashlib
import hmac
import json

import fakeredis
import pytest
import redis
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import main

SECRET = "test-secret"
client = TestClient(main.app)

PR_BODY = json.dumps({
    "action": "opened",
    "pull_request": {"number": 7, "head": {"sha": "abc123"}},
    "repository": {"full_name": "dhiasalah/sentinel-playground"},
    "installation": {"id": 99},
}).encode()


@pytest.fixture(autouse=True)
def fixed_secret(monkeypatch):
    monkeypatch.setattr(main.settings, "github_webhook_secret", SecretStr(SECRET))

@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr(main, "redis_client", fake)
    return fake

def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post(body: bytes, signature: str | None, event: str = "pull_request", delivery: str = "d-1"):
    headers = {"X-GitHub-Event": event, "X-GitHub-Delivery": delivery, "Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return client.post("/webhooks/github", content=body, headers=headers)


def test_signed_pull_request_is_accepted():
    response = post(PR_BODY, sign(PR_BODY))
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "pr": 7}


def test_missing_signature_is_rejected():
    assert post(PR_BODY, None).status_code == 401


def test_wrong_secret_is_rejected():
    assert post(PR_BODY, sign(PR_BODY, "attacker-guess")).status_code == 401


def test_tampered_body_is_rejected():
    tampered = PR_BODY.replace(b'"number": 7', b'"number": 8')
    assert post(tampered, sign(PR_BODY)).status_code == 401


def test_irrelevant_action_is_ignored():
    body = json.dumps({"action": "closed"}).encode()
    response = post(body, sign(body))
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_empty_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(main.settings, "github_webhook_secret", SecretStr(""))
    assert post(PR_BODY, sign(PR_BODY, "")).status_code == 401

def test_accepted_pull_request_is_queued(fake_redis):
    post(PR_BODY, sign(PR_BODY))
    job = json.loads(fake_redis.rpop(main.QUEUE))
    assert job == {"delivery": "d-1", "repo": "dhiasalah/sentinel-playground", "pr": 7,
                   "head_sha": "abc123", "installation_id": 99}


def test_replayed_body_is_queued_once_even_with_new_delivery_id(fake_redis):
    assert post(PR_BODY, sign(PR_BODY), delivery="d-1").status_code == 202
    replay = post(PR_BODY, sign(PR_BODY), delivery="attacker-made-up-id")
    assert replay.json() == {"status": "duplicate"}
    assert fake_redis.llen(main.QUEUE) == 1


def test_redis_down_returns_503(monkeypatch):
    broken = redis.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    monkeypatch.setattr(main, "redis_client", broken)
    assert post(PR_BODY, sign(PR_BODY)).status_code == 503
