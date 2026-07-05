"""LLM service layer.

Wraps LiteLLM to provide a thin abstraction over chat completion calls for
multiple providers: OpenAI, Anthropic, Google (Gemini), OpenRouter, and local
OpenAI-compatible endpoints (Ollama, LM Studio, llama.cpp server, ...).

API keys are resolved from the OS keyring (via :mod:`ganesh_backend.services.config`)
with a fallback to the ``{PROVIDER}_API_KEY`` environment variable. The resolved
key is cached per-provider for the lifetime of the process so repeated requests
do not hit the keyring backend (which can be slow on some platforms).

The ``local`` provider is special: it requires no API key (a placeholder is
sent), routes to a user-configured ``api_base`` (``llm.local.base_url``), and
fetches model listings from the endpoint's OpenAI-compatible ``/v1/models``
endpoint rather than from a static registry.

LiteLLM model-prefix conventions:
    - openai: plain model name (e.g. ``gpt-4o-mini``)
    - anthropic: plain model name (litellm auto-detects the ``claude-`` prefix)
    - google: ``gemini/<model>`` (litellm requires the ``gemini/`` prefix)
    - openrouter: ``openrouter/<vendor>/<model>`` (litellm requires the
      ``openrouter/`` prefix)
    - local: ``openai/<model>`` with ``api_base`` set to the local endpoint
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Iterator

import httpx
import litellm

from ganesh_backend.services.config import config_service

DEFAULT_PROVIDER: str = "openai"
DEFAULT_MODEL: str = "gpt-4o-mini"

SUPPORTED_PROVIDERS: tuple[str, ...] = (
    "openai",
    "anthropic",
    "google",
    "openrouter",
    "local",
)

PROVIDER_MODELS: dict[str, tuple[str, ...]] = {
    "openai": (
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ),
    "anthropic": (
        "claude-3-5-sonnet-20240620",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ),
    "google": (
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-2.0-flash",
    ),
    "openrouter": (
        "openai/gpt-4o-mini",
        "anthropic/claude-3.5-sonnet",
        "google/gemini-2.0-flash-001",
    ),
    "local": (),
}

_LOCAL_DEFAULT_BASE_URL = "http://localhost:11434/v1"
_LOCAL_PLACEHOLDER_KEY = "not-required"

# Environment variable name for each provider's API key fallback.
_PROVIDER_ENV_VAR: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class MissingAPIKeyError(RuntimeError):
    """Raised when no API key is available from keyring or environment."""


class LLMError(RuntimeError):
    """Generic LLM call failure (rate limit, invalid model, network, ...)."""


class UnsupportedProviderError(ValueError):
    """Raised when an unknown provider name is supplied."""


def _keyring_key(provider: str) -> str:
    """Return the keyring username for a provider's API key."""
    return f"ganesh_api_key_{provider}"


@lru_cache(maxsize=None)
def get_api_key(provider: str = DEFAULT_PROVIDER) -> str:
    """Resolve the API key for ``provider``.

    Order of precedence:
        1. OS keyring (managed by ``config_service``)
        2. ``{PROVIDER}_API_KEY`` environment variable

    The result is cached per-provider for the process lifetime. To force a
    re-read (e.g. after the user updates the key via the config UI) call
    :func:`reset_api_key_cache`.

    The ``local`` provider requires no key — a placeholder is returned.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise UnsupportedProviderError(
            f"Unknown provider: {provider!r}. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    if provider == "local":
        return _LOCAL_PLACEHOLDER_KEY
    key = config_service.get_provider_key(provider)
    if not key:
        env_var = _PROVIDER_ENV_VAR[provider]
        key = config_service.get_provider_key_env(provider) or None
        if not key:
            raise MissingAPIKeyError(
                f"No {provider} API key configured. Set one via the config UI "
                f"or the {env_var} environment variable."
            )
    return key


def reset_api_key_cache() -> None:
    """Clear all cached API keys so the next call re-reads from keyring/env."""
    get_api_key.cache_clear()


def _litellm_model_name(provider: str, model: str) -> str:
    """Translate a (provider, model) pair into a LiteLLM model string.

    LiteLLM uses model-name prefixes to route to non-OpenAI providers. This
    function applies the required prefix for google (``gemini/``),
    openrouter (``openrouter/``), and local (``openai/`` so LiteLLM uses the
    OpenAI provider path against a custom ``api_base``).
    """
    if provider == "google":
        if not model.startswith("gemini/"):
            return f"gemini/{model}"
        return model
    if provider == "openrouter":
        if not model.startswith("openrouter/"):
            return f"openrouter/{model}"
        return model
    if provider == "local":
        if not model.startswith("openai/"):
            return f"openai/{model}"
        return model
    # openai and anthropic use plain model names (litellm auto-detects claude-).
    return model


def _get_local_base_url() -> str:
    """Return the configured local LLM endpoint base URL."""
    return config_service.get_setting(
        "llm.local.base_url", _LOCAL_DEFAULT_BASE_URL
    ) or _LOCAL_DEFAULT_BASE_URL


def get_available_models(provider: str = DEFAULT_PROVIDER) -> list[str]:
    """Return the list of models the service can route to for ``provider``.

    For cloud providers this is a static registry. For ``local`` it fetches
    the model list from the endpoint's OpenAI-compatible ``/v1/models``
    endpoint (``GET {base_url}/models``). Returns an empty list if the
    endpoint is unreachable.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise UnsupportedProviderError(
            f"Unknown provider: {provider!r}. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    if provider == "local":
        base_url = _get_local_base_url().rstrip("/")
        url = f"{base_url}/models"
        try:
            resp = httpx.get(url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []
    return list(PROVIDER_MODELS[provider])


def chat_completion(
    messages: list[dict[str, str]],
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    stream: bool = False,
    tools: list[dict[str, Any]] | None = None,
) -> Any:
    """Call LiteLLM ``completion`` and return the raw response.

    Args:
        messages: OpenAI-style message list (``{"role", "content"}``).
        provider: One of :data:`SUPPORTED_PROVIDERS`.
        model: Model name (provider-specific). Defaults to the provider's
            first entry in :data:`PROVIDER_MODELS`.
        stream: If True, returns a streaming iterator of chunks.
        tools: Optional list of OpenAI-style tool definitions. LiteLLM
            normalizes the format for each provider.

    Raises:
        UnsupportedProviderError: ``provider`` is not in SUPPORTED_PROVIDERS.
        MissingAPIKeyError: No API key configured for the provider.
        LLMError: The underlying LiteLLM call failed.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise UnsupportedProviderError(
            f"Unknown provider: {provider!r}. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    if provider == "local":
        chosen_model = model or config_service.get_setting(
            "llm.local.model", ""
        ) or "local-model"
    else:
        chosen_model = model or PROVIDER_MODELS[provider][0]
    litellm_model = _litellm_model_name(provider, chosen_model)
    api_key = get_api_key(provider)

    kwargs: dict[str, Any] = {
        "model": litellm_model,
        "messages": messages,
        "stream": stream,
        "api_key": api_key,
    }
    if provider == "local":
        kwargs["api_base"] = _get_local_base_url()
    if tools is not None:
        kwargs["tools"] = tools

    try:
        response = litellm.completion(**kwargs)
    except MissingAPIKeyError:
        raise
    except UnsupportedProviderError:
        raise
    except Exception as exc:  # noqa: BLE001 - litellm raises many types
        raise LLMError(str(exc)) from exc

    return response


def stream_chunks(response: Any) -> Iterator[str]:
    """Yield text deltas from a streaming LiteLLM response.

    Args:
        response: The object returned by :func:`chat_completion` with
            ``stream=True``.

    Yields:
        str: Each non-empty content delta.
    """
    for chunk in response:
        try:
            delta = chunk.choices[0].delta.content
        except (AttributeError, IndexError):
            delta = None
        if delta:
            yield delta


def test_connection(provider: str = DEFAULT_PROVIDER) -> bool:
    """Validate the provider's API key by making a minimal completion call.

    Returns ``True`` on success, ``False`` on any LLM error. Raises
    :class:`UnsupportedProviderError` for unknown providers (this is a
    programmer error, not a runtime/config error).

    For the ``local`` provider, validates the endpoint is reachable by
    fetching ``GET {base_url}/models`` rather than making a completion call
    (which would require a model to be loaded).
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise UnsupportedProviderError(
            f"Unknown provider: {provider!r}. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    if provider == "local":
        base_url = _get_local_base_url().rstrip("/")
        try:
            resp = httpx.get(f"{base_url}/models", timeout=10.0)
            resp.raise_for_status()
            return True
        except Exception:
            return False

    try:
        api_key = get_api_key(provider)
    except MissingAPIKeyError:
        return False

    litellm_model = _litellm_model_name(
        provider, PROVIDER_MODELS[provider][0]
    )
    try:
        litellm.completion(
            model=litellm_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            api_key=api_key,
        )
    except Exception:  # noqa: BLE001 - any failure means the key is bad
        return False
    return True
