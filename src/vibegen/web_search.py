"""Stdlib-only web search for LLM context enrichment.

Searches DuckDuckGo, filters results to trusted Python/programming domains,
then fetches and extracts meaningful content from each page.
"""

from __future__ import annotations

import contextlib
import html as html_module
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

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
        # Strip www. prefix
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
    """Convert GitHub blob URLs to raw content URLs for direct fetching.

    Args:
        url: Original URL from DDG results.

    Returns:
        Possibly-rewritten URL that resolves to plain text/HTML content.
    """
    # GitHub blob viewer → raw content
    # https://github.com/owner/repo/blob/main/file.py
    # → https://raw.githubusercontent.com/owner/repo/main/file.py
    gh_blob = re.match(
        r"https://github\.com/([^/]+/[^/]+)/blob/(.+)", url
    )
    if gh_blob:
        return f"https://raw.githubusercontent.com/{gh_blob.group(1)}/{gh_blob.group(2)}"
    return url


# ---------------------------------------------------------------------------
# Page fetching and content extraction
# ---------------------------------------------------------------------------


def _fetch_html(url: str, timeout: int = _FETCH_TIMEOUT) -> str:
    """Fetch *url* and return the response body as a string.

    Args:
        url: Target URL.
        timeout: Request timeout in seconds.

    Returns:
        Response body, or ``""`` on any error.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return ""


def _extract_stackoverflow(html: str) -> str:
    """Prefer the accepted (or top-voted) answer from a Stack Overflow page.

    Finds the first ``accepted-answer`` div; falls back to the first ``answer``
    div if none is accepted.  Both the question body and the answer body are
    included.

    Args:
        html: Full HTML source of the Stack Overflow page.

    Returns:
        Extracted text capped at ``_MAX_CONTENT_CHARS``.
    """
    # Isolate the answer section to extract from.
    answer_html = ""
    for marker in ("accepted-answer", "js-answer"):
        idx = html.find(marker)
        if idx != -1:
            # Find the enclosing div start (scan backwards for <div)
            start = html.rfind("<div", 0, idx)
            if start != -1:
                # Extract a generous chunk after that div
                answer_html = html[start : start + 30_000]
                break

    # Build combined source: question first, then answer.
    # The question body has class "question" around it.
    q_idx = html.find('class="question"')
    question_html = html[max(0, q_idx - 5) : q_idx + 20_000] if q_idx != -1 else ""

    combined = question_html + "\n" + answer_html if answer_html else html
    extractor = _ContentExtractor()
    with contextlib.suppress(Exception):
        extractor.feed(combined)
    return extractor.render()


def _extract_page_content(html: str, url: str) -> str:
    """Dispatch to a site-specific extractor or the generic one.

    Args:
        html: Full HTML (or plain text) of the fetched page.
        url: Original URL (used to detect the site).

    Returns:
        Extracted plain-text content.
    """
    domain = _get_domain(url)

    # Raw content (e.g. GitHub raw files) — return as-is, capped.
    if "raw.githubusercontent.com" in url:
        return html[:_MAX_CONTENT_CHARS]

    if "stackoverflow.com" in domain:
        return _extract_stackoverflow(html)

    extractor = _ContentExtractor()
    with contextlib.suppress(Exception):
        extractor.feed(html)
    return extractor.render()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def web_search(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo, fetch top results from trusted domains, return context.

    The function:
    1. Queries ``html.duckduckgo.com`` for results.
    2. Scores each result by domain (Stack Overflow, Python docs, PyPI, etc.)
       and sorts preferred domains first.
    3. Fetches the actual page content for up to *max_results* URLs.
    4. Returns a formatted plain-text block suitable as LLM context.

    Uses stdlib only — no external dependencies.  Returns ``""`` on any error
    so callers can degrade gracefully.

    Args:
        query: Search query string.
        max_results: Maximum number of results to fetch content from.

    Returns:
        Formatted plain-text block with extracted page content, or ``""``.
    """
    search_url = (
        "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    )
    req = urllib.request.Request(search_url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_SEARCH_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError):
        return ""

    ddg_parser = _DDGParser()
    try:
        ddg_parser.feed(body)
    except Exception:  # noqa: BLE001
        return ""

    if not ddg_parser.results:
        return ""

    # Score and sort: preferred domains first, then by original order.
    scored: list[tuple[int, int, dict[str, str]]] = []
    for idx, result in enumerate(ddg_parser.results):
        url = result.get("url", "").strip()
        if not url:
            continue
        score = _score_url(url)
        scored.append((-score, idx, result))  # negative for descending sort
    scored.sort(key=lambda t: (t[0], t[1]))

    lines: list[str] = ["=== Web Search Results ==="]
    fetched = 0

    for _, _, result in scored:
        if fetched >= max_results:
            break

        raw_url = result.get("url", "").strip()
        title = html_module.unescape(result.get("title", "")).strip()
        snippet = html_module.unescape(result.get("snippet", "")).strip()
        score = _score_url(raw_url)

        fetch_url = _normalize_url(raw_url)
        content = ""
        if score > 0 or fetched < 2:
            # Always attempt to fetch preferred-domain results; also fetch
            # the first two results regardless of domain.
            html_body = _fetch_html(fetch_url)
            if html_body:
                content = _extract_page_content(html_body, fetch_url)

        lines.append(f"\n[{fetched + 1}] {title}")
        lines.append(f"    {raw_url}")
        if content:
            lines.append(f"\n{content}")
        elif snippet:
            # Fall back to DDG snippet when page fetch fails or yields nothing.
            lines.append(f"    {snippet}")

        fetched += 1

    if fetched == 0:
        return ""

    lines.append("\n=== End of Web Search Results ===")
    return "\n".join(lines)
