import traceback
from types import SimpleNamespace

import groq
import httpx
import pytest
from google.genai import errors as genai_errors

from sentinel.llm.providers import BadAnswer, GeminiProvider, GroqProvider, ProviderUnavailable
from sentinel.llm.router import AllProvidersFailed, LLMRouter


class FakeProvider:
    def __init__(self, name, answer=None, error=None):
        self.name = name
        self.answer = answer
        self.error = error
        self.calls = 0

    def complete(self, system, user, json_mode=False):
        self.calls += 1
        if self.error:
            raise self.error
        return self.answer


def test_uses_first_provider_when_it_works():
    first = FakeProvider("gemini", answer="hi")
    second = FakeProvider("groq", answer="hello")
    result = LLMRouter([first, second]).complete("sys", "user")
    assert result.provider == "gemini"
    assert second.calls == 0


def test_falls_back_when_first_is_unavailable():
    first = FakeProvider("gemini", error=ProviderUnavailable("429"))
    second = FakeProvider("groq", answer="hello")
    result = LLMRouter([first, second]).complete("sys", "user")
    assert result.provider == "groq"
    assert result.text == "hello"


def test_does_not_hide_real_bugs():
    first = FakeProvider("gemini", error=ValueError("bad model name"))
    second = FakeProvider("groq", answer="hello")
    with pytest.raises(ValueError):
        LLMRouter([first, second]).complete("sys", "user")
    assert second.calls == 0


def test_falls_back_when_the_answer_is_unusable():
    def check(text):
        if text != "good":
            raise BadAnswer("dropped findings")

    first = FakeProvider("gemini", answer="bad")
    second = FakeProvider("groq", answer="good")
    result = LLMRouter([first, second]).complete("sys", "user", check=check)
    assert (result.provider, result.text) == ("groq", "good")


def test_raises_when_all_providers_fail():
    providers = [
        FakeProvider("gemini", error=ProviderUnavailable("429")),
        FakeProvider("groq", error=ProviderUnavailable("503")),
    ]
    with pytest.raises(AllProvidersFailed):
        LLMRouter(providers).complete("sys", "user")


class RaisingModels:
    def __init__(self, code):
        self.code = code

    def generate_content(self, **kwargs):
        raise genai_errors.APIError(self.code, {"error": {"code": self.code, "message": "m", "status": "S"}})


@pytest.mark.parametrize("code", [408, 429, 499, 503, 504])
def test_gemini_transient_errors_trigger_fallback(code):
    provider = GeminiProvider(api_key="test", model="m")
    provider._client = SimpleNamespace(models=RaisingModels(code))
    with pytest.raises(ProviderUnavailable):
        provider.complete("sys", "user")


def test_gemini_client_errors_are_not_hidden():
    provider = GeminiProvider(api_key="test", model="m")
    provider._client = SimpleNamespace(models=RaisingModels(400))
    with pytest.raises(genai_errors.APIError):
        provider.complete("sys", "user")


def groq_raising(code):
    body = {"error": {"message": "m", "code": code, "failed_generation": '{"issues": "LEAKED REPO TEXT"'}}
    response = httpx.Response(400, request=httpx.Request("POST", "https://groq.test"), json=body)

    def create(**kwargs):
        raise groq.BadRequestError(f"Error code: 400 - {body}", response=response, body=body)

    provider = GroqProvider(api_key="test", model="m")
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return provider


def test_groq_invalid_json_is_a_bad_answer_that_does_not_leak_it():
    with pytest.raises(BadAnswer) as info:
        groq_raising("json_validate_failed").complete("sys", "user", json_mode=True)
    assert "LEAKED" not in "".join(traceback.format_exception(info.value))


def test_groq_other_bad_requests_are_not_hidden():
    with pytest.raises(groq.BadRequestError):
        groq_raising("model_not_found").complete("sys", "user", json_mode=True)


def groq_status(status):
    body = {"error": {"message": "Request too large", "type": "tokens", "code": "rate_limit_exceeded"}}
    response = httpx.Response(status, request=httpx.Request("POST", "https://groq.test"), json=body)

    def create(**kwargs):
        raise groq.APIStatusError(f"Error code: {status} - {body}", response=response, body=body)

    provider = GroqProvider(api_key="test", model="m")
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return provider


def test_groq_request_too_large_falls_back():
    with pytest.raises(ProviderUnavailable):
        groq_status(413).complete("sys", "user", json_mode=True)


def test_groq_other_status_errors_are_not_hidden():
    with pytest.raises(groq.APIStatusError):
        groq_status(418).complete("sys", "user", json_mode=True)

def test_repo_setting_picks_the_first_provider_and_keeps_the_other_as_fallback():
    from pydantic import SecretStr

    from sentinel.config import Settings
    from sentinel.llm.router import build_router

    settings = Settings(gemini_api_key=SecretStr("g"), groq_api_key=SecretStr("q"), _env_file=None)
    assert [p.name for p in build_router(settings)._providers] == ["gemini", "groq"]
    assert [p.name for p in build_router(settings, ["groq", "gemini"])._providers] == ["groq", "gemini"]
    assert [p.name for p in build_router(settings, ["groq"])._providers] == ["groq", "gemini"]
