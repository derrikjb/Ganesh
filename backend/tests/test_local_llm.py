"""Tests for local LLM support via OpenAI-compatible endpoints.

The local provider routes through LiteLLM with ``api_base`` pointing at a
user-configured endpoint (Ollama, LM Studio, llama.cpp server, ...). No API
key is required. Model listings are fetched from the endpoint's
``/v1/models`` (OpenAI-compatible) endpoint.

LiteLLM and httpx are mocked throughout — no real HTTP calls are made.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch, MagicMock

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


def _make_models_response(model_ids: list[str]):
    """Build a mock httpx.Response for an OpenAI-compatible /v1/models call."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "object": "list",
        "data": [{"id": mid, "object": "model"} for mid in model_ids],
    }
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def test_local_chat():
    """Local provider routes through LiteLLM with api_base, no real key needed."""
    mock_response = _make_response("Hi from local LLM", "llama3.2")
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=mock_response,
    ) as mock_completion, patch(
        "ganesh_backend.services.llm.config_service.get_setting",
        side_effect=lambda key, default=None: {
            "llm.local.base_url": "http://localhost:11434/v1",
            "llm.local.model": "llama3.2",
        }.get(key, default),
    ):
        result = llm_service.chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            provider="local",
            model="llama3.2",
        )
    assert result.choices[0].message.content == "Hi from local LLM"
    _, kwargs = mock_completion.call_args
    # LiteLLM routes to the custom OpenAI-compatible endpoint via api_base.
    assert kwargs["api_base"] == "http://localhost:11434/v1"
    # No real API key required — a placeholder is sent.
    assert kwargs["api_key"] == "not-required"
    # Model is prefixed with openai/ so LiteLLM uses the OpenAI provider path.
    assert kwargs["model"] == "openai/llama3.2"


def test_local_model_listing():
    """get_available_models('local') fetches models from the local endpoint."""
    mock_http_response = _make_models_response(["llama3.2", "qwen2.5", "phi3"])
    with patch(
        "ganesh_backend.services.llm.httpx.get",
        return_value=mock_http_response,
    ) as mock_get, patch(
        "ganesh_backend.services.llm.config_service.get_setting",
        side_effect=lambda key, default=None: {
            "llm.local.base_url": "http://localhost:11434/v1",
        }.get(key, default),
    ):
        models = llm_service.get_available_models("local")
    assert models == ["llama3.2", "qwen2.5", "phi3"]
    # Should have fetched from {base_url}/models.
    mock_get.assert_called_once()
    call_url = mock_get.call_args[0][0] if mock_get.call_args[0] else mock_get.call_args[1].get("url")
    assert call_url == "http://localhost:11434/v1/models"


def test_local_no_key():
    """Local provider does NOT raise MissingAPIKeyError when no key is set."""
    # get_api_key('local') should return a placeholder, never raise.
    with patch(
        "ganesh_backend.services.config.config_service.get_provider_key",
        return_value=None,
    ), patch(
        "ganesh_backend.services.config.config_service.get_provider_key_env",
        return_value=None,
    ):
        key = llm_service.get_api_key("local")
    assert key == "not-required"


def test_local_test_connection_success():
    """test_connection('local') validates the endpoint is reachable."""
    mock_http_response = _make_models_response(["llama3.2"])
    with patch(
        "ganesh_backend.services.llm.httpx.get",
        return_value=mock_http_response,
    ), patch(
        "ganesh_backend.services.llm.config_service.get_setting",
        side_effect=lambda key, default=None: {
            "llm.local.base_url": "http://localhost:11434/v1",
        }.get(key, default),
    ):
        ok = llm_service.test_connection("local")
    assert ok is True


def test_local_test_connection_failure():
    """test_connection('local') returns False when endpoint is unreachable."""
    import httpx as _httpx
    with patch(
        "ganesh_backend.services.llm.httpx.get",
        side_effect=_httpx.ConnectError("connection refused"),
    ), patch(
        "ganesh_backend.services.llm.config_service.get_setting",
        side_effect=lambda key, default=None: {
            "llm.local.base_url": "http://localhost:11434/v1",
        }.get(key, default),
    ):
        ok = llm_service.test_connection("local")
    assert ok is False


def test_local_models_router_endpoint():
    """GET /api/config/providers/local/models fetches from the local endpoint."""
    mock_http_response = _make_models_response(["llama3.2", "qwen2.5"])
    with patch(
        "ganesh_backend.services.llm.httpx.get",
        return_value=mock_http_response,
    ), patch(
        "ganesh_backend.services.llm.config_service.get_setting",
        side_effect=lambda key, default=None: {
            "llm.local.base_url": "http://localhost:11434/v1",
        }.get(key, default),
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.get("/api/config/providers/local/models")
    assert response.status_code == 200
    models = response.json()["models"]
    assert "llama3.2" in models
    assert "qwen2.5" in models


def test_local_test_router_endpoint():
    """POST /api/config/providers/local/test validates the local endpoint."""
    mock_http_response = _make_models_response(["llama3.2"])
    with patch(
        "ganesh_backend.services.llm.httpx.get",
        return_value=mock_http_response,
    ), patch(
        "ganesh_backend.services.llm.config_service.get_setting",
        side_effect=lambda key, default=None: {
            "llm.local.base_url": "http://localhost:11434/v1",
        }.get(key, default),
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post("/api/config/providers/local/test")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_local_endpoint_config_storage():
    """POST /api/config/providers/local/endpoint stores base_url + model."""
    with patch(
        "ganesh_backend.services.config.config_service.set_setting"
    ) as mock_set:
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/config/providers/local/endpoint",
                json={
                    "base_url": "http://localhost:11434/v1",
                    "model": "llama3.2",
                },
            )
    assert response.status_code == 200
    # Should have stored both llm.local.base_url and llm.local.model.
    set_calls = {call.args[0]: call.args[1] for call in mock_set.call_args_list}
    assert set_calls["llm.local.base_url"] == "http://localhost:11434/v1"
    assert set_calls["llm.local.model"] == "llama3.2"


def test_local_chat_router():
    """Chat router routes local provider with api_base from config."""
    mock_response = _make_response("local-resp", "llama3.2")
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=mock_response,
    ) as mock_completion, patch(
        "ganesh_backend.services.llm.config_service.get_setting",
        side_effect=lambda key, default=None: {
            "llm.local.base_url": "http://localhost:11434/v1",
            "llm.local.model": "llama3.2",
        }.get(key, default),
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "provider": "local",
                    "model": "llama3.2",
                },
            )
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "local-resp"
    assert body["provider"] == "local"
    _, kwargs = mock_completion.call_args
    assert kwargs["api_base"] == "http://localhost:11434/v1"
