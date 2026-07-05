"""Tests for multi-provider LLM support (Anthropic, Google, OpenRouter).

LiteLLM is mocked throughout — no real API calls are made.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import main as main_module
from ganesh_backend.services import llm as llm_service


@pytest.fixture(autouse=True)
def _reset_caches():
    llm_service.reset_api_key_cache()
    yield
    llm_service.reset_api_key_cache()


def _make_response(content: str = "hello", model: str = "mock-model"):
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
    )


def _make_tool_response(tool_name: str, arguments: str):
    return SimpleNamespace(
        model="mock-model",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            type="function",
                            function=SimpleNamespace(
                                name=tool_name,
                                arguments=arguments,
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
    )


def test_anthropic_chat():
    """Anthropic provider routes through LiteLLM with claude- prefix."""
    mock_response = _make_response("Hi from Claude", "claude-3-5-sonnet-20240620")
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=mock_response,
    ) as mock_completion, patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="anthropic-key",
    ):
        result = llm_service.chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            provider="anthropic",
            model="claude-3-5-sonnet-20240620",
        )
    assert result.choices[0].message.content == "Hi from Claude"
    _, kwargs = mock_completion.call_args
    assert kwargs["model"] == "claude-3-5-sonnet-20240620"
    assert kwargs["api_key"] == "anthropic-key"


def test_google_chat():
    """Google provider routes through LiteLLM with gemini/ prefix."""
    mock_response = _make_response("Hi from Gemini", "gemini-1.5-flash")
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=mock_response,
    ) as mock_completion, patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="google-key",
    ):
        result = llm_service.chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            provider="google",
            model="gemini-1.5-flash",
        )
    assert result.choices[0].message.content == "Hi from Gemini"
    _, kwargs = mock_completion.call_args
    # LiteLLM requires the gemini/ prefix for Google models.
    assert kwargs["model"] == "gemini/gemini-1.5-flash"
    assert kwargs["api_key"] == "google-key"


def test_openrouter_chat():
    """OpenRouter provider routes through LiteLLM with openrouter/ prefix."""
    mock_response = _make_response("Hi from OpenRouter", "openai/gpt-4o-mini")
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=mock_response,
    ) as mock_completion, patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="openrouter-key",
    ):
        result = llm_service.chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            provider="openrouter",
            model="openai/gpt-4o-mini",
        )
    assert result.choices[0].message.content == "Hi from OpenRouter"
    _, kwargs = mock_completion.call_args
    assert kwargs["model"] == "openrouter/openai/gpt-4o-mini"
    assert kwargs["api_key"] == "openrouter-key"


def test_provider_switching():
    """Switching providers routes to the correct LiteLLM model prefix."""
    responses = {
        "openai": _make_response("openai-resp", "gpt-4o-mini"),
        "anthropic": _make_response("anthropic-resp", "claude-3-5-sonnet-20240620"),
        "google": _make_response("google-resp", "gemini-1.5-flash"),
        "openrouter": _make_response("or-resp", "openai/gpt-4o-mini"),
    }
    captured_models: list[str] = []

    def fake_completion(*args, **kwargs):
        captured_models.append(kwargs["model"])
        # Return the matching response by matching the captured model.
        for resp in responses.values():
            if resp.model == kwargs.get("model") or resp.model in kwargs.get(
                "model", ""
            ):
                return resp
        return list(responses.values())[0]

    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        side_effect=fake_completion,
    ), patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="key",
    ):
        llm_service.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            provider="openai",
            model="gpt-4o-mini",
        )
        llm_service.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            provider="anthropic",
            model="claude-3-5-sonnet-20240620",
        )
        llm_service.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            provider="google",
            model="gemini-1.5-flash",
        )
        llm_service.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            provider="openrouter",
            model="openai/gpt-4o-mini",
        )

    assert captured_models == [
        "gpt-4o-mini",
        "claude-3-5-sonnet-20240620",
        "gemini/gemini-1.5-flash",
        "openrouter/openai/gpt-4o-mini",
    ]


def test_tool_calling_anthropic():
    """Tool calling with Anthropic provider — adapter normalizes tool_calls."""
    mock_response = _make_tool_response("get_weather", '{"city": "SF"}')
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=mock_response,
    ) as mock_completion, patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="anthropic-key",
    ):
        result = llm_service.chat_completion(
            messages=[{"role": "user", "content": "weather in SF?"}],
            provider="anthropic",
            model="claude-3-5-sonnet-20240620",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get weather",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "city": {"type": "string"}
                            },
                            "required": ["city"],
                        },
                    },
                }
            ],
        )
    _, kwargs = mock_completion.call_args
    # Tools must be passed through to LiteLLM (the adapter normalizes format).
    assert "tools" in kwargs
    assert kwargs["tools"][0]["function"]["name"] == "get_weather"
    # Response should expose normalized tool_calls.
    msg = result.choices[0].message
    assert msg.tool_calls is not None
    assert msg.tool_calls[0].function.name == "get_weather"
    assert msg.tool_calls[0].function.arguments == '{"city": "SF"}'


def test_get_available_models_per_provider():
    """get_available_models returns models for each provider."""
    openai_models = llm_service.get_available_models("openai")
    assert "gpt-4o-mini" in openai_models
    anthropic_models = llm_service.get_available_models("anthropic")
    assert any("claude" in m for m in anthropic_models)
    google_models = llm_service.get_available_models("google")
    assert any("gemini" in m for m in google_models)
    openrouter_models = llm_service.get_available_models("openrouter")
    assert any("openrouter" in m or "/" in m for m in openrouter_models)


def test_test_connection_validates_key():
    """test_connection makes a minimal call to validate the API key."""
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=_make_response("ok", "gpt-4o-mini"),
    ) as mock_completion, patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="test-key",
    ):
        ok = llm_service.test_connection("openai")
    assert ok is True
    _, kwargs = mock_completion.call_args
    # Should make a tiny call (max_tokens small).
    assert kwargs.get("max_tokens") is not None and kwargs["max_tokens"] <= 10


def test_test_connection_failure():
    """test_connection returns False on LLMError."""
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        side_effect=llm_service.LLMError("401 invalid"),
    ), patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="bad-key",
    ):
        ok = llm_service.test_connection("openai")
    assert ok is False


def test_chat_router_accepts_provider():
    """Chat router accepts provider and model in request body."""
    mock_response = _make_response("router-resp", "claude-3-5-sonnet-20240620")
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=mock_response,
    ), patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="anthropic-key",
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20240620",
                },
            )
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "router-resp"


def test_chat_router_defaults_to_openai():
    """Chat router defaults to openai provider when not specified."""
    mock_response = _make_response("default-resp", "gpt-4o-mini")
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=mock_response,
    ) as mock_completion, patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="openai-key",
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    assert response.status_code == 200
    _, kwargs = mock_completion.call_args
    assert kwargs["model"] == "gpt-4o-mini"


def test_chat_router_rejects_unknown_provider():
    """Unknown provider returns 400."""
    with patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="key",
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "provider": "unknown",
                },
            )
    assert response.status_code == 400


def test_config_providers_endpoint():
    """GET /api/config/providers lists configured providers."""
    with patch(
        "ganesh_backend.services.config.config_service.get_provider_key",
        side_effect=lambda p: "key" if p == "openai" else None,
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.get("/api/config/providers")
    assert response.status_code == 200
    providers = response.json()["providers"]
    by_name = {p["name"]: p for p in providers}
    assert by_name["openai"]["configured"] is True
    assert by_name["anthropic"]["configured"] is False


def test_config_provider_key_storage():
    """POST /api/config/providers/{provider}/key stores the key."""
    with patch(
        "ganesh_backend.services.config.config_service.set_provider_key"
    ) as mock_set, patch(
        "ganesh_backend.services.llm.reset_api_key_cache"
    ) as mock_reset:
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/config/providers/anthropic/key",
                json={"api_key": "sk-ant-xxx"},
            )
    assert response.status_code == 200
    mock_set.assert_called_once_with("anthropic", "sk-ant-xxx")
    mock_reset.assert_called_once()


def test_config_provider_models_endpoint():
    """GET /api/config/providers/{provider}/models lists models."""
    client = TestClient(main_module.create_app())
    with client:
        response = client.get("/api/config/providers/anthropic/models")
    assert response.status_code == 200
    models = response.json()["models"]
    assert any("claude" in m for m in models)
