import logging
import sys
from typing import Callable, Sequence

from pydantic import BaseModel

from sentinel.config import Settings
from sentinel.llm.providers import BadAnswer, GeminiProvider, GroqProvider, Provider, ProviderUnavailable

log = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    provider: str
    text: str


class AllProvidersFailed(Exception):
    def __init__(self, message: str, errors: list[Exception] | None = None):
        super().__init__(message)
        self.errors = errors or []


class LLMRouter:
    def __init__(self, providers: list[Provider]):
        self._providers = providers

    def complete(self, system: str, user: str, json_mode: bool = False,
                 check: Callable[[str], object] | None = None) -> LLMResponse:
        failures, errors = [], []
        for provider in self._providers:
            try:
                text = provider.complete(system, user, json_mode=json_mode)
                if check:
                    check(text)
                return LLMResponse(provider=provider.name, text=text)
            except (ProviderUnavailable, BadAnswer) as e:
                log.warning("provider %s failed (%s: %s), falling back", provider.name, type(e).__name__, e)
                failures.append(f"{provider.name}: {e}")
                errors.append(e)
        raise AllProvidersFailed("; ".join(failures), errors)


def build_router(settings: Settings, order: Sequence[str] = ("gemini", "groq")) -> LLMRouter:
    """order: which provider is asked first (repo setting). Every provider stays as a fallback."""
    providers = {
        "gemini": lambda: GeminiProvider(settings.gemini_api_key.get_secret_value(), settings.gemini_model),
        "groq": lambda: GroqProvider(settings.groq_api_key.get_secret_value(), settings.groq_model),
    }
    return LLMRouter([providers[name]() for name in dict.fromkeys([*order, *providers])])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    router = build_router(Settings())
    result = router.complete(
        system="You are a concise assistant. Answer in one sentence.",
        user=" ".join(sys.argv[1:]),
    )
    print(f"[{result.provider}] {result.text}")
