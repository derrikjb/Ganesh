"""Web search service for Ganesh.

Uses the DuckDuckGo HTML endpoint (https://html.duckduckgo.com/html/)
which requires no API key and returns a parseable HTML page of search
results. Results are extracted via regex and returned as plain dicts so
the router layer can serialise them directly to JSON.
"""
from __future__ import annotations

import re
from html import unescape
from typing import Any, TypedDict
from urllib.parse import parse_qs, unquote, urlparse

import httpx

DDG_HTML_URL = "https://html.duckduckgo.com/html/"
DEFAULT_NUM_RESULTS = 5
MAX_NUM_RESULTS = 20
REQUEST_TIMEOUT = 10.0

# A browser-like User-Agent is required — DuckDuckGo returns a 403 to
# the default httpx UA string.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class SearchResult(TypedDict):
    title: str
    url: str
    snippet: str


# Matches <a class="result__a" ... href="...uddg=ENCODED_URL...">TITLE</a>
# and the immediately following <a class="result__snippet" ...>SNIPPET</a>.
# DuckDuckGo wraps real URLs in a /l/?uddg=<encoded> redirect; we extract
# and decode the uddg parameter to recover the destination URL.
_RESULT_RE = re.compile(
    r'class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'.*?class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.DOTALL,
)


def _extract_destination_url(href: str) -> str:
    """Pull the real destination URL out of a DuckDuckGo redirect href."""
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    uddg = params.get("uddg", [href])
    return unquote(uddg[0])


def _strip_tags(text: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()


def parse_results(html: str, num_results: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for match in _RESULT_RE.finditer(html):
        if len(results) >= num_results:
            break
        results.append(
            SearchResult(
                title=_strip_tags(match.group("title")),
                url=_extract_destination_url(match.group("href")),
                snippet=_strip_tags(match.group("snippet")),
            )
        )
    return results


async def web_search(
    query: str,
    num_results: int = DEFAULT_NUM_RESULTS,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[SearchResult]:
    """Perform a web search and return structured results.

    On rate-limiting (HTTP 429) or network errors, returns an empty list
    rather than raising — search is a best-effort tool.
    """
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)

    try:
        response = await client.post(
            DDG_HTML_URL,
            data={"q": query},
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        if response.status_code == 429:
            return []
        response.raise_for_status()
        return parse_results(response.text, num_results)
    except httpx.HTTPError:
        return []
    finally:
        if owns_client:
            await client.aclose()


def to_dict_list(results: list[SearchResult]) -> list[dict[str, Any]]:
    return [dict(r) for r in results]
