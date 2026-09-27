# Week 2 · Step 2.2 — LLM router (Gemini primary, Groq fallback)

## 🎯 Goal

One Python function, `router.complete(system, user)`, that asks **Gemini** first and automatically
switches to **Groq** if Gemini is rate-limited or down. Every agent (triage in 2.3, planner and fixer
later) will talk to LLMs **only** through this router, never to a provider directly.

## 🧰 Tools in this step

### LLM API call (what actually happens)

- You send an HTTPS request with your **API key** and two texts: a **system prompt** (the rules: "You
  are a security reviewer, answer in JSON...") and a **user prompt** (the actual task and data). The
  model sends back text. That's all an "AI agent" is at its core: code that builds prompts, calls this,
  and acts on the answer.
- **Temperature**: how "creative" (random) the answer is. `0` = the most predictable answer, which is what
  you want for security triage: the same finding should get the same verdict every time.

### SDKs: `google-genai` and `groq`

- **What they are:** official Python libraries that wrap each provider's HTTP API, so you call a method instead
  of building HTTP requests by hand. Each provider has a **different** SDK with different method names,
  response shapes and error classes. The router hides these differences.
  [google-genai](https://googleapis.github.io/python-genai/) · [groq](https://console.groq.com/docs/libraries)

### Rate limits and HTTP error codes

- Free tiers allow only N requests per minute/day. Go over it and you get **HTTP 429 Too Many
  Requests**. **5xx** errors mean the provider itself is broken right now. Both are **temporary**, so try another provider.
- **4xx** errors other than 429 (400 bad request, 401 bad key, 404 unknown model) mean **your** config or code is
  wrong. Switching provider would only **hide the bug**, so these must fail loudly.

### Provider abstraction (a `Protocol`)

- **What it is:** a Python "interface": any class with a `name` and a `complete(system, user) -> str`
  method counts as a provider. Analogy: power adapters. Every country's socket is different, but your
  laptop only knows "the plug". Gemini and Groq are sockets, and the adapter classes make them look the same.
- **Why:** the router loops over a list of providers without caring which is which. Adding OpenRouter
  or a local model later = one new adapter class. Tests can plug in **fake** providers (no network, no keys).
  [typing.Protocol](https://docs.python.org/3/library/typing.html#typing.Protocol)

### `logging`

- The stdlib way to record what happened (`INFO`, `WARNING`, ...) instead of `print`. In week 10 these
  logs + Langfuse traces show _which_ provider answered and how often you fell back. [Docs](https://docs.python.org/3/library/logging.html)

### How it connects

```
 triage agent (2.3) ──▶ router.complete(system, user)
                              │
                              ├─▶ GeminiProvider ──▶ Gemini API ── OK ──▶ LLMResponse(provider="gemini", text=...)
                              │        │
                              │        └─ 429 / 5xx / timeout → ProviderUnavailable → log warning, next ↓
                              │
                              └─▶ GroqProvider   ──▶ Groq API   ── OK ──▶ LLMResponse(provider="groq", text=...)
                                       │
                                       └─ also unavailable → AllProvidersFailed

   400 / 401 / 404 anywhere → raised immediately (a bug, not bad luck)
```

## 💻 Commands

**Where:** `agents/requirements.txt` becomes:

```
pydantic
pydantic-settings
google-genai
groq
```

From `agents/`, venv active:

```powershell
pip install -r requirements-dev.txt
New-Item sentinel/config.py
New-Item -ItemType Directory sentinel/llm
New-Item sentinel/llm/__init__.py, sentinel/llm/providers.py, sentinel/llm/router.py, tests/test_router.py
```

Expected: `Successfully installed google-genai-... groq-... pydantic-settings-...` (plus their dependencies, such as `httpx`).

Add the model names to your **root** `.env` **and** `.env.example` (below the keys):

```dotenv
GEMINI_MODEL=gemini-2.5-flash
GROQ_MODEL=llama-3.3-70b-versatile
```

Model names change often. If you get a _404 model not found_, check the current lists
([Gemini models](https://ai.google.dev/gemini-api/docs/models) · [Groq models](https://console.groq.com/docs/models))
and change **only `.env`**, not code.

## 🧩 Code, piece by piece

### 1. Agent settings

**Where:** `agents/sentinel/config.py`

```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    gemini_api_key: SecretStr
    groq_api_key: SecretStr
    gemini_model: str = "gemini-2.5-flash"
    groq_model: str = "llama-3.3-70b-versatile"
```

The same pattern as the API's config (lesson 1.5), but `../.env` because `agents/` is one level below the
root. There's one difference on purpose: **no `settings = Settings()` at the bottom**. The object is created only
when something calls `Settings()`, so importing router code in tests doesn't require real keys, and CI (week 9)
can run the unit tests without secrets.

### 2. Errors the router understands

**Where:** `agents/sentinel/llm/providers.py`, at the top.

```python
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
```

`ProviderUnavailable` is **your own** exception: each adapter translates its SDK's errors into it when the
problem is temporary. The router then only has to catch one type, and never needs to know that Gemini
calls it `APIError(code=429)` and Groq calls it `RateLimitError`. `Provider` is the "plug shape" described above.

### 3. The Gemini adapter

**Where:** same file, below.

```python
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
```

- `timeout=30_000` is in **milliseconds** (30s), so a hanging request becomes a fallback instead of a frozen worker.
- `system_instruction` = the rules and `contents` = the task. Keeping them separate matters for prompt-injection
  defense in 2.3: untrusted code goes in the user part, never in the rules.
- 429/5xx → `ProviderUnavailable` (try Groq). Any other API error → re-raised as-is (your bug, fail loudly).
- `httpx.TransportError` covers timeouts and connection failures (`google-genai` uses `httpx` under the hood).
- `from e` keeps the original error attached, so the traceback still shows the real cause.
- `response.text or ""`: `text` can be `None` (e.g. the response was blocked by safety filters), and the router
  always returns a string.

### 4. The Groq adapter

**Where:** same file, below.

```python
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
```

Groq uses the **OpenAI-style** chat format: a list of messages with roles, and the answer is in `choices[0]`.
This is the format most providers copy. `max_retries=0` turns off the SDK's own automatic retries (by default it
waits and retries twice). Your router already has a better plan B (another provider), so retrying the same
rate-limited service just wastes seconds. `APIConnectionError` also covers timeouts.

### 5. The router

**Where:** `agents/sentinel/llm/router.py`, at the top.

```python
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
```

The router tries providers **in order**, and the list order _is_ the priority. It only catches `ProviderUnavailable`,
so a bad key or unknown model propagates immediately. It returns an `LLMResponse` that records **who** answered,
which you'll want in the report, in cost tracking and when debugging "why did the answer change?" (different model!).
`log.warning("... %s", x)` (not an f-string) is the logging idiom: the text is only formatted if the log level is enabled.

### 6. Build the real router + try it

**Where:** same file, at the bottom.

```python
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
```

`build_router` is the **only** place real keys are read (`get_secret_value()`), and they go straight into the
clients and nowhere else. Gemini comes first because it's the primary; swap the list to change priority.

### 7. Test the fallback logic with fake providers

**Where:** `agents/tests/test_router.py`

```python
import pytest

from sentinel.llm.providers import ProviderUnavailable
from sentinel.llm.router import AllProvidersFailed, LLMRouter


class FakeProvider:
    def __init__(self, name, answer=None, error=None):
        self.name = name
        self.answer = answer
        self.error = error
        self.calls = 0

    def complete(self, system, user):
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
```

`FakeProvider` fits the `Provider` plug (it has `name` + `complete`) without inheriting anything. That's how
`Protocol` works ("duck typing"). These 4 tests pin down the router's whole contract: priority,
fallback, **not** falling back on bugs, and the all-down case. They run in milliseconds, with no keys and no network.
`calls` lets a test prove that Groq was **not** contacted.

## 📚 Key concepts

- **Retryable vs non-retryable errors:** the core design decision of any resilient client. Retry or fall back
  on _temporary_ problems, and fail fast on _your_ mistakes.
- **Adapter pattern:** wrap each vendor's API behind your own interface. You're never locked into one provider.
- **Graceful degradation:** the free tiers _will_ rate-limit you during demos. With fallback, users see a slightly
  different model instead of an error.

## 🔐 Security note

- Keys only leave `SecretStr` inside `build_router`. **Never log** prompts that may contain secrets, and never log keys
  (the SDKs don't, and neither do your log lines, which only contain provider names and error codes).
- **Data privacy:** what you send to Gemini's free tier may be used by Google. Only demo or public code.
- A fallback provider is also a **different trust boundary**: the same prompt now goes to a second company.
  Document it (README, week 10), because users of a security tool care where their code is sent.
- Prompt injection (malicious instructions hidden in scanned code) is step 2.3's topic. The system/user split
  you built here is its foundation.

## ✅ Check it works

Unit tests (from `agents/`, venv active):

```powershell
python -m pytest -v
```

Expected: `6 passed` (2 Semgrep + 4 router).

Real call:

```powershell
python -m sentinel.llm.router "What is SQL injection?"
```

Expected (wording varies):

```
[gemini] SQL injection is an attack where malicious input is inserted into a database query ...
```

**See the "fail loudly" rule:** in `.env`, set `GEMINI_MODEL=gemini-does-not-exist`, run it again, then revert.
Expected: a traceback ending in a **404** `ClientError` about the model, and **no** fallback to Groq. Your
config bug is shown to you, not hidden.

**The fallback itself** is proven by `test_falls_back_when_first_is_unavailable`, so you don't need to break
Gemini on purpose. You'll see a real `WARNING ... falling back` line the first time Gemini rate-limits you
during triage in 2.3.

## ⚠️ Gotcha: `404 NOT_FOUND` on the first real call

`models/gemini-2.5-flash is no longer available to new users` → model names get retired. Fix = config, not code:
list the models your key can use, then set `GEMINI_MODEL` in `.env` (+ `.env.example` and the default in `config.py`).
Note the router **did not** fall back to Groq, and that's correct: 404 is a permanent config error, not a
temporary outage. Falling back would hide the misconfiguration forever (and silently cost you Gemini's free tier).

## 🛠️ Also fix (from the 2.1 review)

**Where:** `agents/sentinel/scanners/semgrep.py`, first lines of `run_semgrep`, right after `target = target.resolve()`:

```python
    if not target.is_dir():
        raise FileNotFoundError(f"scan target is not a directory: {target}")
```

With a typo in the path, Docker Desktop silently **creates an empty folder** for the mount, and Semgrep reports
`0 findings`. For a security tool, a scan that silently found nothing is the worst kind of bug. Check your inputs.

Commit (from repo root):

```powershell
git add agents .env.example
git status
git commit -m "feat(agents): LLM router with Gemini primary and Groq fallback"
git push
```

Check that `git status` shows `.env.example` but **not** `.env`.

## ➡️ Next step

**2.3: LLM triage** (deduplicate your 9 Semgrep findings, explain them, rank severity, structured JSON output,
and defend against prompt injection). Tell Claude **"I finished step 2.2, please review"**.
