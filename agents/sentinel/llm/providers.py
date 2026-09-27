from typing import Protocol

import groq
import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types


class ProviderUnavailable(Exception):
    """Temporary failure (rate limit, outage, timeout): the router should try the next provider."""


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...

class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(timeout=30_000),
        )
        self._model = model

    def complete(self, system: str, user: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user,
                config=genai_types.GenerateContentConfig(system_instruction=system, temperature=0),
            )
        except genai_errors.APIError as e:
            if e.code == 429 or e.code >= 500:
                raise ProviderUnavailable(f"gemini returned {e.code}") from e
            raise
        except httpx.TransportError as e:
            raise ProviderUnavailable(f"gemini network error: {type(e).__name__}") from e
        return response.text or ""

class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str):
        self._client = groq.Groq(api_key=api_key, timeout=30, max_retries=0)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
            )
        except (groq.RateLimitError, groq.InternalServerError, groq.APIConnectionError) as e:
            raise ProviderUnavailable(f"groq: {type(e).__name__}") from e
        return response.choices[0].message.content or ""
