import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
from sentinel.github.auth import make_app_jwt,get_installation_token


def test_app_jwt_is_signed_and_short_lived():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    token = make_app_jwt(42, pem, now=1_000_000)
    claims = jwt.decode(
        token, key.public_key(), algorithms=["RS256"], options={"verify_exp": False}
    )

    assert claims == {"iat": 999_940, "exp": 1_000_540, "iss": "42"}
    assert claims["exp"] - claims["iat"] <= 600

def test_installation_token_is_downscoped(monkeypatch):
    calls = {}

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls.update(kwargs)
        return httpx.Response(201, json={"token": "ghs_fake"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    assert get_installation_token("jwt", 99, "sentinel-playground", {"contents": "read"}) == "ghs_fake"
    assert calls["url"].endswith("/app/installations/99/access_tokens")
    assert calls["json"] == {"repositories": ["sentinel-playground"], "permissions": {"contents": "read"}}
