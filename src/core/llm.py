from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pydantic import SecretStr

from core.api_keys import ValidationResult
from core.config import (
    DEFAULT_GOOGLE_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    LLM_PROVIDER_ID,
    OPENROUTER_BASE_URL,
    logger,
)


APP_ATTRIBUTION_URL = "https://github.com/sak0x7d5/LearnIslamAI"
APP_ATTRIBUTION_TITLE = "IslamAI"

# One probe request answers three questions at once: is the key accepted, does
# the model exist, and can it call tools. Tool calling is not optional here --
# a model that answers from its own memory instead of calling the search tools
# produces fluent religious claims with no citations, which is worse than an
# error. The probe is what keeps that failure out of the answer path.
PROBE_TIMEOUT_SECONDS = 30
PROBE_PROMPT = "Call the islamai_probe tool with ok set to true."

# Statuses that are not credential problems still need an actionable message.
# These are fixed literals: no provider text or exception message is ever
# formatted into a result, because provider errors echo request bodies.
_STATUS_HINTS = {
    "400": "the request was rejected; check the configured model name",
    "402": "the account has no credit for that model; add credit or choose a free model",
    "404": "the configured model was not found",
    "429": "the account is rate limited; wait and try again",
}


@dataclass(frozen=True)
class Provider:
    """A generation backend. Everything downstream speaks only langchain_core."""

    id: str
    label: str
    key_env: str
    model_env: str
    default_model: str
    console_url: str
    key_placeholder: str
    factory: Callable[[str, SecretStr, int | None], Any]
    # Statuses meaning "this credential is wrong". Per-provider on purpose:
    # Gemini answers 400 for a malformed key, while OpenRouter answers 400 for
    # a bad model or parameter. A shared set would misreport one of them.
    rejecting_statuses: frozenset[str]

    def build(self, model: str, api_key: SecretStr, *, max_retries: int | None = None) -> Any:
        """Construct a chat client. The key is always passed explicitly."""
        return self.factory(model, api_key, max_retries)


def _build_google(model: str, api_key: SecretStr, max_retries: int | None) -> Any:
    from langchain_google_genai import ChatGoogleGenerativeAI

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "google_api_key": api_key,
    }
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    return ChatGoogleGenerativeAI(**kwargs)


def _build_openrouter(model: str, api_key: SecretStr, max_retries: int | None) -> Any:
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "api_key": api_key,
        "base_url": OPENROUTER_BASE_URL,
        # OpenRouter serves /chat/completions only, never OpenAI's Responses API.
        "use_responses_api": False,
        "default_headers": {
            "HTTP-Referer": APP_ATTRIBUTION_URL,
            "X-Title": APP_ATTRIBUTION_TITLE,
        },
    }
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    return ChatOpenAI(**kwargs)


GOOGLE = Provider(
    id="google",
    label="Google Gemini",
    key_env="GOOGLE_API_KEY",
    model_env="GEMINI_MODEL",
    default_model=DEFAULT_GOOGLE_MODEL,
    console_url="https://aistudio.google.com/apikey",
    key_placeholder="Enter your Google API key",
    factory=_build_google,
    rejecting_statuses=frozenset({"400", "401", "403", "unauthenticated", "permission_denied"}),
)

OPENROUTER = Provider(
    id="openrouter",
    label="OpenRouter",
    key_env="OPENROUTER_API_KEY",
    model_env="OPENROUTER_MODEL",
    default_model=DEFAULT_OPENROUTER_MODEL,
    console_url="https://openrouter.ai/keys",
    key_placeholder="Enter your OpenRouter API key",
    factory=_build_openrouter,
    rejecting_statuses=frozenset({"401", "403"}),
)

# Order is the auto-detection tie-break, so an existing Gemini install keeps
# working untouched even when both keys happen to be present.
PROVIDERS: tuple[Provider, ...] = (GOOGLE, OPENROUTER)

# A fresh install with no key at all is sent to the free router.
FALLBACK_PROVIDER = OPENROUTER


class ProviderError(RuntimeError):
    """An actionable provider-configuration problem. Never carries secrets."""


def provider_by_id(provider_id: str) -> Provider | None:
    wanted = provider_id.strip().lower()
    return next((item for item in PROVIDERS if item.id == wanted), None)


def resolve_provider(
    read_secret: Callable[[str], SecretStr | None],
    configured_id: str = LLM_PROVIDER_ID,
) -> Provider:
    """Honour an explicit choice, else pick the provider whose key is present."""

    if configured_id:
        chosen = provider_by_id(configured_id)
        if chosen is not None:
            return _checked(chosen)
        logger.warning(
            "Unknown ISLAMAI_LLM_PROVIDER %r; detecting from the configured key instead. "
            "Valid values: %s.",
            configured_id,
            ", ".join(item.id for item in PROVIDERS),
        )

    for candidate in PROVIDERS:
        if read_secret(candidate.key_env) is not None:
            return _checked(candidate)
    return _checked(FALLBACK_PROVIDER)


def _checked(provider: Provider) -> Provider:
    """Refuse a configuration that would put a key on the wire in plaintext."""

    if provider is OPENROUTER and not OPENROUTER_BASE_URL.startswith("https://"):
        raise ProviderError("OPENROUTER_BASE_URL must be an HTTPS URL.")
    return provider


def resolve_model(provider: Provider) -> str:
    """Read the model at call time, matching how config reads GEMINI_MODEL."""

    configured = os.environ.get(provider.model_env, "").strip()
    return configured or provider.default_model


def classify_failure(provider: Provider, model: str, exc: BaseException) -> ValidationResult:
    """Map a provider exception to a status without leaking its text or the key."""

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        logger.warning("%s did not answer the validation probe in time.", provider.label)
        return ValidationResult(
            "unavailable",
            f"{provider.label} did not respond in time. Check the network and try again.",
        )

    raw = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    status = str(raw).lower() if raw is not None else ""
    logger.warning(
        "%s key validation failed (%s).",
        provider.label,
        type(exc).__name__,
    )

    if status in provider.rejecting_statuses:
        return ValidationResult("invalid", f"{provider.label} rejected this API key.")

    # Anything else is a configuration or availability problem, so report it as
    # "unavailable": that stops the key prompt instead of looping for another
    # key, which could never fix a missing credit balance or a bad model name.
    hint = _STATUS_HINTS.get(status, "it was unavailable; check the network")
    return ValidationResult(
        "unavailable",
        f"The key could not be validated with {provider.label} for the model "
        f"'{model}' because {hint}. Then try again.",
    )


async def probe_tool_calling(provider: Provider, model: str, key: SecretStr) -> bool:
    """Return whether the model answered a forced tool call with a real one."""

    @tool
    def islamai_probe(ok: bool) -> str:
        """Confirm tool calling works. Call this with ok=true."""
        return "ok"

    client = provider.build(model, key, max_retries=0)
    # "any" is accepted by both provider classes as "you must call a tool", so
    # a capable model that merely chose not to call one cannot fail the probe.
    bound = client.bind_tools([islamai_probe], tool_choice="any")
    response = await bound.ainvoke([HumanMessage(content=PROBE_PROMPT)])
    return bool(getattr(response, "tool_calls", None))


def make_key_validator(
    provider: Provider,
    model: str,
    probe: Callable[[Provider, str, SecretStr], Awaitable[bool]] = probe_tool_calling,
) -> Callable[[SecretStr], Awaitable[ValidationResult]]:
    """Build the validator ApiKeyService owns, bound to one provider and model."""

    async def validate(key: SecretStr) -> ValidationResult:
        try:
            supports_tools = await asyncio.wait_for(
                probe(provider, model, key), timeout=PROBE_TIMEOUT_SECONDS
            )
        except Exception as exc:  # provider exception types vary between SDK releases
            return classify_failure(provider, model, exc)

        if not supports_tools:
            # The key is fine, so do not ask for another one.
            return ValidationResult(
                "unavailable",
                f"{provider.label} accepted the key, but the model '{model}' did not "
                "return a tool call. IslamAI needs a model that supports tool calling "
                f"to search the Quran and Hadith corpus. Set {provider.model_env} to a "
                "tool-capable model and try again.",
            )
        return ValidationResult("valid", f"{provider.label} API key validated.")

    return validate
