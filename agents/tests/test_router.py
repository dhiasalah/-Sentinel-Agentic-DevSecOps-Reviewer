from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from sentinel.llm.providers import GeminiProvider, ProviderUnavailable
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
