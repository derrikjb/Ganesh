"""Tests for the web search service and router.

No real HTTP requests are made — all responses are served via
httpx.MockTransport with canned DuckDuckGo HTML payloads.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

import main as main_module
from ganesh_backend.routers.search import get_search_client
from ganesh_backend.services.search import web_search

# Mirrors the structure of https://html.duckduckgo.com/html/ result pages:
# each result is an <a class="result__a" href="...uddg=ENCODED...">title</a>
# followed by <a class="result__snippet" ...>snippet</a>. The uddg query
# parameter holds the URL-encoded destination URL.
DDG_HTML_SAMPLE = """
<html><body>
<div class="result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a"
       href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.python.org%2F&rut=abc">
      Welcome to Python.org
    </a>
  </h2>
  <a class="result__snippet"
     href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.python.org%2F&rut=abc">
    The official home of the Python programming language.
  </a>
</div>
<div class="result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a"
       href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Ftutorial%2F&rut=def">
      Python Tutorial — Python 3 documentation
    </a>
  </h2>
  <a class="result__snippet"
     href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Ftutorial%2F&rut=def">
    This tutorial introduces the reader informally to the basic concepts of Python.
  </a>
</div>
</body></html>
""".strip()


def _make_mock_client(
    status_code: int = 200,
    body: str = DDG_HTML_SAMPLE,
) -> httpx.AsyncClient:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            status_code, text=body, headers={"content-type": "text/html"}
        )
    )
    return httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_web_search() -> None:
    client = _make_mock_client()
    try:
        results = await web_search("python programming", num_results=5, client=client)
    finally:
        await client.aclose()

    assert len(results) > 0
    assert len(results) <= 5


@pytest.mark.asyncio
async def test_web_search_result_format() -> None:
    client = _make_mock_client()
    try:
        results = await web_search("python", num_results=2, client=client)
    finally:
        await client.aclose()

    assert len(results) == 2
    for r in results:
        assert isinstance(r["title"], str) and r["title"]
        assert isinstance(r["url"], str) and r["url"].startswith("http")
        assert isinstance(r["snippet"], str)


@pytest.mark.asyncio
async def test_web_search_rate_limit() -> None:
    client = _make_mock_client(status_code=429, body="rate limited")
    try:
        results = await web_search("anything", num_results=5, client=client)
    finally:
        await client.aclose()

    assert results == []


def test_web_search_empty_query() -> None:
    client = TestClient(main_module.create_app())
    with client:
        response = client.get("/api/search", params={"query": ""})
    assert response.status_code == 400


def test_search_router_returns_results() -> None:
    mock_client = _make_mock_client()

    async def _override() -> httpx.AsyncClient:
        return mock_client

    app = main_module.create_app()
    app.dependency_overrides[get_search_client] = _override

    client = TestClient(app)
    try:
        with client:
            response = client.get(
                "/api/search", params={"query": "python", "limit": 2}
            )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert {"title", "url", "snippet"} <= set(data[0].keys())
    finally:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(mock_client.aclose())
        loop.close()
