"""Stdlib-only web search for LLM context enrichment.

Supports multiple search providers via a Protocol interface:
- DuckDuckGo (default, no API key required)
- Google Custom Search (requires GOOGLE_API_KEY + GOOGLE_SEARCH_ENGINE_ID env vars)

Results are scored by domain priority, fetched, and text-extracted.
"""

from __future__ import annotations

import contextlib
import html as html_module
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Protocol

# ---------------------------------------------------------------------------
# Domain configuration
# ---------------------------------------------------------------------------

# Preferred domains with priority scores (higher = fetched first).
_DOMAIN_SCORES: dict[str, int] = {
    "stackoverflow.com": 10,
    "docs.python.org": 10,
    "peps.python.org": 9,
    "packaging.python.org": 9,
    "python.org": 9,
    "pypi.org": 8,
    "realpython.com": 8,
    "pytest.org": 8,
    "readthedocs.io": 7,
    "github.com": 6,
    "raw.githubusercontent.com": 6,
}

_UA = "Mozilla/5.0 (compatible; vibegen/1.0)"
_SEARCH_TIMEOUT = 10
_FETCH_TIMEOUT = 6
_MAX_CONTENT_CHARS = 2_500

# HTML regions to skip entirely.
_SKIP_TAGS: frozenset[str] = frozenset(
    {"script", "style", "head", "noscript", "iframe", "svg", "form"}
)
_SKIP_ROLES: frozenset[str] = frozenset(
    {"navigation", "banner", "complementary", "search", "contentinfo"}
)
# CSS class substrings that signal boilerplate.
_SKIP_CSS: tuple[str, ...] = (
    "nav",
    "navbar",
    "footer",
    "header",
    "sidebar",
    "cookie",
    "banner",
    "advertisement",
    "promo",
    "breadcrumb",
    "pagination",
    "related",
    "comment",
    "menu",
    "toc",
    "share",
    "social",
    "subscribe",
    "signup",
)
_BLOCK_TAGS: frozenset[str] = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "main",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "li",
        "blockquote",
        "td",
        "th",
        "dt",
        "dd",
    }
)


# ---------------------------------------------------------------------------
# Search provider protocol
# ---------------------------------------------------------------------------


class SearchResult:
    """A single search result with URL, title, and snippet.

    Attributes:
        url: Target page URL.
        title: Page title from the search engine.
        snippet: Short description from the search engine.
    """

    __slots__ = ("url", "title", "snippet")

    def __init__(self, url: str, title: str, snippet: str) -> None:
        self.url = url
        self.title = title
        self.snippet = snippet


class SearchProvider(Protocol):
    """Protocol for search provider implementations."""

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Execute a search and return up to *max_results* results.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.

        Returns:
            List of SearchResult objects (may be empty).
        """
        ...


# ---------------------------------------------------------------------------
# DuckDuckGo result parser
# ---------------------------------------------------------------------------


class _DDGParser(HTMLParser):
    """Extract result titles, URLs, and snippets from DuckDuckGo HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture: str | None = None  # "title" | "snippet"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        css = attr_dict.get("class", "") or ""

        if tag == "a" and "result__a" in css:
            href = attr_dict.get("href", "") or ""
            self._current = {"url": href, "title": "", "snippet": ""}
            self._capture = "title"
        elif tag in {"a", "div"} and "result__snippet" in css:
            if self._current is not None:
                self._capture = "snippet"

    def handle_data(self, data: str) -> None:
        if self._capture and self._current is not None:
            self._current[self._capture] += data

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "title" and tag == "a":
            self._capture = None
        elif self._capture == "snippet" and tag in {"a", "div"}:
            if self._current is not None:
                self.results.append(self._current)
                self._current = None
            self._capture = None


class DuckDuckGoProvider:
    """Search provider backed by DuckDuckGo HTML (stdlib only, no API key)."""

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Query DuckDuckGo HTML and return parsed results.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.

        Returns:
            List of SearchResult objects, empty on any error.
        """
        search_url = (
            "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
        )
        req = urllib.request.Request(search_url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=_SEARCH_TIMEOUT) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError):
            return []

        parser = _DDGParser()
        with contextlib.suppress(Exception):
            parser.feed(body)

        results: list[SearchResult] = []
        for r in parser.results[:max_results]:
            url = r.get("url", "").strip()
            if url:
                results.append(
                    SearchResult(
                        url=url,
                        title=html_module.unescape(r.get("title", "")).strip(),
                        snippet=html_module.unescape(r.get("snippet", "")).strip(),
                    )
                )
        return results


class GoogleProvider:
    """Search provider backed by Google Custom Search JSON API.

    Requires environment variables:
    - ``GOOGLE_API_KEY``: Google API key with Custom Search enabled.
    - ``GOOGLE_SEARCH_ENGINE_ID``: Programmable Search Engine ID (cx parameter).
    """

    _API_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self) -> None:
        self.api_key = os.environ.get("GOOGLE_API_KEY", "")
        self.cx = os.environ.get("GOOGLE_SEARCH_ENGINE_ID", "")

    @classmethod
    def is_available(cls) -> bool:
        """Return True when both required env vars are set."""
        return bool(
            os.environ.get("GOOGLE_API_KEY") and
            os.environ.get("GOOGLE_SEARCH_ENGINE_ID")
        )

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Query the Google Custom Search API and return parsed results.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return (capped at 10 by API).

        Returns:
            List of SearchResult objects, empty on any error.
        """
        if not self.api_key or not self.cx:
            return []

        params = urllib.parse.urlencode({
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": min(max_results, 10),
        })
        req = urllib.request.Request(
            f"{self._API_URL}?{params}", headers={"User-Agent": _UA}
        )
        try:
            with urllib.request.urlopen(req, timeout=_SEARCH_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return []

        results: list[SearchResult] = []
        for item in data.get("items", []):
            url = item.get("link", "").strip()
            if url:
                results.append(
                    SearchResult(
                        url=url,
                        title=item.get("title", "").strip(),
                        snippet=item.get("snippet", "").strip(),
                    )
                )
        return results


def _default_providers() -> list[SearchProvider]:
    """Return the ordered provider list based on available credentials.

    Google is preferred when credentials are present; DuckDuckGo is always
    included as fallback.

    Returns:
        Ordered list of SearchProvider instances.
    """
    providers: list[SearchProvider] = []
    if GoogleProvider.is_available():
        providers.append(GoogleProvider())
    providers.append(DuckDuckGoProvider())
    return providers


# ---------------------------------------------------------------------------
# Generic page content extractor
# ---------------------------------------------------------------------------


class _ContentExtractor(HTMLParser):
    """Convert HTML to clean plaintext, preserving code blocks.

    Skips navigation, footers, sidebars, cookie banners, and similar
    boilerplate regions.  Collects paragraphs and code blocks in document
    order so the LLM receives coherent, contextual content.
    """

    def __init__(self) -> None:
        super().__init__()
        # (type, text) entries: type is "text" or "code"
        self._entries: list[tuple[str, str]] = []
        self._skip_depth: int = 0
        self._code_depth: int = 0
        self._buf: list[str] = []

    # ------------------------------------------------------------------
    # HTMLParser callbacks
    # ------------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth > 0:
            if tag in _SKIP_TAGS:
                self._skip_depth += 1
            return

        attr_dict = dict(attrs)
        css = (attr_dict.get("class") or "").lower()
        role = (attr_dict.get("role") or "").lower()

        if (
            tag in _SKIP_TAGS
            or role in _SKIP_ROLES
            or any(hint in css for hint in _SKIP_CSS)
        ):
            self._flush()
            self._skip_depth += 1
            return

        if tag in {"pre", "code"}:
            self._flush()
            self._code_depth += 1
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth > 0:
            if tag in _SKIP_TAGS:
                self._skip_depth -= 1
            return

        if tag in {"pre", "code"}:
            self._code_depth = max(0, self._code_depth - 1)
            self._flush(is_code=True)
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._code_depth > 0:
            self._buf.append(data)
        else:
            text = data.strip()
            if text:
                self._buf.append(text)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _flush(self, is_code: bool = False) -> None:
        sep = "" if is_code else " "
        text = sep.join(self._buf).strip()
        self._buf = []
        if not text:
            return
        self._entries.append(("code" if is_code else "text", text))

    def render(self, max_chars: int = _MAX_CONTENT_CHARS) -> str:
        """Return extracted content as a clean string, capped at *max_chars*."""
        self._flush()
        parts: list[str] = []
        total = 0
        for entry_type, text in self._entries:
            if total >= max_chars:
                break
            remaining = max_chars - total
            chunk = text[:remaining]
            formatted = f"```\n{chunk}\n```" if entry_type == "code" else chunk
            parts.append(formatted)
            total += len(formatted) + 2
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# URL utilities
# ---------------------------------------------------------------------------


def _get_domain(url: str) -> str:
    """Return the registrable domain portion of *url* (e.g. ``stackoverflow.com``)."""
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        return host.removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


def _score_url(url: str) -> int:
    """Return the priority score for *url* (0 if not a preferred domain)."""
    domain = _get_domain(url)
    for pattern, score in _DOMAIN_SCORES.items():
        if domain == pattern or domain.endswith("." + pattern):
            return score
    return 0


def _normalize_url(url: str) -> str:
    """Convert GitHub blob URLs to raw content URLs for direct fetching."""
    gh_blob = re.match(
        r"https://github\.com/([^/]+/[^/]+)/blob/(.+)", url
    )
    if gh_blob:
        return (
            f"https://raw.githubusercontent.com/{gh_blob.group(1)}/{gh_blob.group(2)}"
        )
    return url


# ---------------------------------------------------------------------------
# Page fetching and content extraction
# ---------------------------------------------------------------------------


def _fetch_html(url: str, timeout: int = _FETCH_TIMEOUT) -> str:
    """Fetch *url* and return the response body as a string."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return ""


def _extract_stackoverflow(html: str) -> str:
    """Prefer the accepted (or top-voted) answer from a Stack Overflow page."""
    answer_html = ""
    for marker in ("accepted-answer", "js-answer"):
        idx = html.find(marker)
        if idx != -1:
            start = html.rfind("<div", 0, idx)
            if start != -1:
                answer_html = html[start : start + 30_000]
                break

    q_idx = html.find('class="question"')
    question_html = html[max(0, q_idx - 5) : q_idx + 20_000] if q_idx != -1 else ""

    combined = question_html + "\n" + answer_html if answer_html else html
    extractor = _ContentExtractor()
    with contextlib.suppress(Exception):
        extractor.feed(combined)
    return extractor.render()


def _extract_page_content(html: str, url: str) -> str:
    """Dispatch to a site-specific extractor or the generic one."""
    if "raw.githubusercontent.com" in url:
        return html[:_MAX_CONTENT_CHARS]

    domain = _get_domain(url)
    if "stackoverflow.com" in domain:
        return _extract_stackoverflow(html)

    extractor = _ContentExtractor()
    with contextlib.suppress(Exception):
        extractor.feed(html)
    return extractor.render()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def web_search(
    query: str,
    max_results: int = 5,
    providers: list[SearchProvider] | None = None,
) -> str:
    """Search the web, fetch top results from trusted domains, return context.

    Uses a provider chain (Google if credentials present, else DuckDuckGo).
    Results are scored by domain priority (Stack Overflow, Python docs, PyPI,
    GitHub, etc.), fetched, and text-extracted for LLM consumption.

    Args:
        query: Search query string.
        max_results: Maximum number of results to fetch content from.
        providers: Override the default provider chain.  Each provider is
            tried in order; results are de-duplicated by URL.

    Returns:
        Formatted plain-text block with extracted page content, or ``""``.
    """
    if providers is None:
        providers = _default_providers()

    # Collect results from all providers, de-duplicate by URL.
    seen_urls: set[str] = set()
    all_results: list[SearchResult] = []
    for provider in providers:
        for r in provider.search(query, max_results):
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                all_results.append(r)
        if len(all_results) >= max_results:
            break

    if not all_results:
        return ""

    # Score and sort: preferred domains first, then by original order.
    scored: list[tuple[int, int, SearchResult]] = []
    for idx, result in enumerate(all_results):
        score = _score_url(result.url)
        scored.append((-score, idx, result))
    scored.sort(key=lambda t: (t[0], t[1]))

    lines: list[str] = ["=== Web Search Results ==="]
    fetched = 0

    for _, _, result in scored:
        if fetched >= max_results:
            break

        score = _score_url(result.url)
        fetch_url = _normalize_url(result.url)
        content = ""
        if score > 0 or fetched < 2:
            html_body = _fetch_html(fetch_url)
            if html_body:
                content = _extract_page_content(html_body, fetch_url)

        lines.append(f"\n[{fetched + 1}] {result.title}")
        lines.append(f"    {result.url}")
        if content:
            lines.append(f"\n{content}")
        elif result.snippet:
            lines.append(f"    {result.snippet}")

        fetched += 1

    if fetched == 0:
        return ""

    lines.append("\n=== End of Web Search Results ===")
    return "\n".join(lines)
