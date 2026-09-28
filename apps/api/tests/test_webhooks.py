import hashlib
import hmac
import json

import pytest
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


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post(body: bytes, signature: str | None, event: str = "pull_request"):
    headers = {"X-GitHub-Event": event, "X-GitHub-Delivery": "d-1", "Content-Type": "application/json"}
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
