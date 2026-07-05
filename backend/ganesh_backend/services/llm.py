"""LLM service layer.

Wraps LiteLLM to provide a thin abstraction over chat completion calls.
API keys are resolved from the OS keyring (via :mod:`ganesh_backend.services.config`)
with a fallback to the ``OPENAI_API_KEY`` environment variable. The resolved key
is cached for the lifetime of the process so repeated requests do not hit the
keyring backend (which can be slow on some platforms).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Iterator

import litellm

from ganesh_backend.services.config import config_service

DEFAULT_MODEL: str = "gpt-4o-mini"

SUPPORTED_MODELS: tuple[str, ...] = (
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
)


class MissingAPIKeyError(RuntimeError):
    """Raised when no API key is available from keyring or environment."""


class LLMError(RuntimeError):
    """Generic LLM call failure (rate limit, invalid model, network, ...)."""


@lru_cache(maxsize=1)
def get_api_key() -> str:
    """Resolve the OpenAI API key.

    Order of precedence:
        1. OS keyring (managed by ``config_service``)
        2. ``OPENAI_API_KEY`` environment variable

    The result is cached for the process lifetime. To force a re-read (e.g.
    after the user updates the key via the config UI) call
    :func:`reset_api_key_cache`.
    """
    key = config_service.get_api_key()
    if not key:
        raise MissingAPIKeyError(
            "No OpenAI API key configured. Set one via the config UI or the "
            "OPENAI_API_KEY environment variable."
        )
    return key


def reset_api_key_cache() -> None:
    """Clear the cached API key so the next call re-reads from keyring/env."""
    get_api_key.cache_clear()


def get_available_models() -> list[str]:
    """Return the list of models the service can route to."""
    return list(SUPPORTED_MODELS)


def chat_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    stream: bool = False,
) -> Any:
    """Call LiteLLM ``completion`` and return the raw response.

    Args:
        messages: OpenAI-style message list (``{"role", "content"}``).
        model: Model name. Defaults to :data:`DEFAULT_MODEL`.
        stream: If True, returns a streaming iterator of chunks.

    Raises:
        MissingAPIKeyError: No API key configured.
        LLMError: The underlying LiteLLM call failed.
    """
    chosen_model = model or DEFAULT_MODEL
    api_key = get_api_key()

    try:
        response = litellm.completion(
            model=chosen_model,
            messages=messages,
            stream=stream,
            api_key=api_key,
        )
    except MissingAPIKeyError:
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
