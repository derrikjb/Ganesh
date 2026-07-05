"""FastAPI router exposing the web search service over HTTP."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from ganesh_backend.services.search import (
    DEFAULT_NUM_RESULTS,
    MAX_NUM_RESULTS,
    web_search,
)

router = APIRouter(prefix="/api", tags=["search"])


async def get_search_client() -> httpx.AsyncClient:
    """Default dependency: a fresh AsyncClient per request.

    Tests override this with a MockTransport-backed client to avoid
    real HTTP traffic.
    """
    return httpx.AsyncClient(timeout=10.0)


@router.get("/search")
async def search(
    query: str = Query(..., description="Search query string"),
    limit: int = Query(DEFAULT_NUM_RESULTS, ge=1, le=MAX_NUM_RESULTS),
    client: httpx.AsyncClient = Depends(get_search_client),
) -> list[dict[str, str]]:
    if not query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    results = await web_search(query, num_results=limit, client=client)
    await client.aclose()
    return [dict(r) for r in results]
