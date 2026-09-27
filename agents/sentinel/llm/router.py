import logging
import sys

from pydantic import BaseModel

from sentinel.config import Settings
from sentinel.llm.providers import GeminiProvider, GroqProvider, Provider, ProviderUnavailable

log = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    provider: str
    text: str


class AllProvidersFailed(Exception):
    pass


class LLMRouter:
    def __init__(self, providers: list[Provider]):
        self._providers = providers

    def complete(self, system: str, user: str) -> LLMResponse:
        failures = []
        for provider in self._providers:
            try:
                text = provider.complete(system, user)
                return LLMResponse(provider=provider.name, text=text)
            except ProviderUnavailable as e:
                log.warning("provider %s unavailable (%s), falling back", provider.name, e)
                failures.append(f"{provider.name}: {e}")
        raise AllProvidersFailed("; ".join(failures))


def build_router(settings: Settings) -> LLMRouter:
    return LLMRouter([
        GeminiProvider(settings.gemini_api_key.get_secret_value(), settings.gemini_model),
        GroqProvider(settings.groq_api_key.get_secret_value(), settings.groq_model),
    ])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    router = build_router(Settings())
    result = router.complete(
        system="You are a concise assistant. Answer in one sentence.",
        user=" ".join(sys.argv[1:]),
    )
    print(f"[{result.provider}] {result.text}")
