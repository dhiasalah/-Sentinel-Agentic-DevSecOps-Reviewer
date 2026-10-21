import logging
import sys
from typing import Callable, Sequence

from langfuse import Langfuse
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
    def __init__(self, providers: list[Provider], langfuse: Langfuse | None = None):
        self._providers = providers
        self._langfuse = langfuse or tracing_off()

    def complete(self, system: str, user: str, json_mode: bool = False,
                 check: Callable[[str], object] | None = None) -> LLMResponse:
        failures, errors = [], []
        sizes = {"system_chars": len(system), "user_chars": len(user), "json_mode": json_mode}
        with self._langfuse.start_as_current_observation(name="llm-call", input=sizes) as call:
            for provider in self._providers:
                with self._langfuse.start_as_current_observation(
                    name=provider.name, as_type="generation", model=getattr(provider, "model", None), input=sizes,
                ) as attempt:
                    try:
                        text = provider.complete(system, user, json_mode=json_mode)
                        attempt.update(usage_details=getattr(provider, "last_usage", None))
                        if check:
                            check(text)
                        attempt.update(output={"answer_chars": len(text)})
                        call.update(output={"answered_by": provider.name, "attempts": len(failures) + 1})
                        return LLMResponse(provider=provider.name, text=text)
                    except (ProviderUnavailable, BadAnswer) as e:
                        log.warning("provider %s failed (%s: %s), falling back", provider.name, type(e).__name__, e)
                        attempt.update(level="ERROR", status_message=f"{type(e).__name__}: {e}")
                        failures.append(f"{provider.name}: {e}")
                        errors.append(e)
            call.update(level="ERROR", status_message="every provider failed")
        raise AllProvidersFailed("; ".join(failures), errors)


def build_router(settings: Settings, order: Sequence[str] = ("gemini", "groq")) -> LLMRouter:
    """order: which provider is asked first (repo setting). Every provider stays as a fallback."""
    providers = {
        "gemini": lambda: GeminiProvider(settings.gemini_api_key.get_secret_value(), settings.gemini_model),
        "groq": lambda: GroqProvider(settings.groq_api_key.get_secret_value(), settings.groq_model),
    }
    return LLMRouter([providers[name]() for name in dict.fromkeys([*order, *providers])], build_langfuse(settings))


def tracing_off() -> Langfuse:
    # the dummy keys only silence Langfuse's "no public_key" warning: with tracing off, nothing is ever sent
    return Langfuse(public_key="off", secret_key="off", tracing_enabled=False)


def build_langfuse(settings: Settings) -> Langfuse:
    """Real client only when both keys are set; otherwise tracing is off (tests, CI, a laptop without keys)."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return tracing_off()
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    router = build_router(Settings())
    result = router.complete(
        system="You are a concise assistant. Answer in one sentence.",
        user=" ".join(sys.argv[1:]),
    )
    print(f"[{result.provider}] {result.text}")
