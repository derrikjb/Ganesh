"""Tests for the /api/chat endpoint.

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
def _reset_api_key_cache():
    llm_service.reset_api_key_cache()
    yield
    llm_service.reset_api_key_cache()


def _make_non_stream_response(content: str = "hello there", model: str = "gpt-4o-mini"):
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
    )


def _make_stream_chunks(deltas: list[str]):
    chunks = []
    for d in deltas:
        chunks.append(
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=d),
                        finish_reason=None,
                    )
                ]
            )
        )
    chunks.append(
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=None),
                    finish_reason="stop",
                )
            ]
        )
    )
    return chunks


def test_chat_endpoint():
    mock_response = _make_non_stream_response("Hi from the model")
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=mock_response,
    ), patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="test-key",
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "Hi from the model"
    assert body["model"] == "gpt-4o-mini"


def test_chat_streaming():
    chunks = _make_stream_chunks(["Hello", " world", "!"])
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=iter(chunks),
    ) as mock_completion, patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="test-key",
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "data:" in body
    assert "Hello" in body
    assert " world" in body
    assert "!" in body
    assert "event: done" in body
    args, kwargs = mock_completion.call_args
    assert kwargs.get("stream") is True


def test_chat_missing_api_key():
    with patch(
        "ganesh_backend.services.llm.get_api_key",
        side_effect=llm_service.MissingAPIKeyError("no key"),
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    assert response.status_code == 401
    assert "no key" in response.json()["detail"]


def test_chat_invalid_model():
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        side_effect=llm_service.LLMError("Invalid model: bad-model"),
    ), patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="test-key",
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "model": "bad-model",
                },
            )
    assert response.status_code == 400
    assert "Invalid model" in response.json()["detail"]
