import pytest

from sentinel.llm.providers import ProviderUnavailable
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
