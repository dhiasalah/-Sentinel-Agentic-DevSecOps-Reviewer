from typing import Protocol

import groq
import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types


class ProviderUnavailable(Exception):
    """Temporary failure (rate limit, outage, timeout): the router should try the next provider."""


class BadAnswer(Exception):
    """The provider answered, but the answer is unusable: the router should try the next provider."""


class Provider(Protocol):
    name: str
    model: str
    last_usage: dict[str, int] | None

    def complete(self, system: str, user: str, json_mode: bool = False) -> str: ...

class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=30_000),
        )
        self.model = model
        self.last_usage = None

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        self.last_usage = None
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=user,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0,
                    response_mime_type="application/json" if json_mode else None,
                    automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )

        except genai_errors.APIError as e:
            # 408 timeout, 429 rate limit, 499 CANCELLED (Google gives up server-side), 5xx outage
            if e.code in (408, 429, 499) or e.code >= 500:
                raise ProviderUnavailable(f"gemini returned {e.code}") from e
            raise
        except httpx.TransportError as e:
            raise ProviderUnavailable(f"gemini network error: {type(e).__name__}") from e
        usage = response.usage_metadata
        if usage:
            # thinking tokens are billed as output, so they count as output here too
            self.last_usage = {"input": usage.prompt_token_count or 0,
                               "output": (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)}
        return response.text or ""

class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str):
        self._client = groq.Groq(api_key=api_key, timeout=30, max_retries=0)
        self.model = model
        self.last_usage = None

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        self.last_usage = None
        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                **extra,
            )

        except (groq.RateLimitError, groq.InternalServerError, groq.APIConnectionError) as e:
            raise ProviderUnavailable(f"groq: {type(e).__name__}") from e
        except groq.BadRequestError as e:
            error = e.body.get("error", {}) if isinstance(e.body, dict) else {}
            if error.get("code") == "json_validate_failed":
                # the error carries the model's whole broken answer (repo-derived text): keep it out of logs
                raise BadAnswer("groq returned invalid JSON") from None
            raise
        except groq.APIStatusError as e:
            if e.status_code == 413:  # prompt over the tier's tokens-per-minute budget: a quota, not a bug
                raise ProviderUnavailable("groq: request too large") from e
            raise
        if response.usage:
            self.last_usage = {"input": response.usage.prompt_tokens, "output": response.usage.completion_tokens}
        return response.choices[0].message.content or ""
