"""Stdlib-only DuckDuckGo web search for LLM context enrichment."""

from __future__ import annotations

import html as html_module
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser


class _DDGParser(HTMLParser):
    """Extract result titles, URLs, and snippets from DuckDuckGo HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture: str | None = None  # "title" | "snippet" | None

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


def web_search(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo and return a plain-text summary of top results.

    Uses stdlib only (no external dependencies). Returns an empty string on
    any network or parsing error so callers can degrade gracefully.

    Args:
        query: Search query string.
        max_results: Maximum number of results to include.

    Returns:
        Formatted plain-text block with titles, URLs, and snippets, or ""
        on failure.
    """
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; vibegen/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError):
        return ""

    parser = _DDGParser()
    try:
        parser.feed(body)
    except Exception:  # noqa: BLE001
        return ""

    if not parser.results:
        return ""

    lines: list[str] = ["=== Web Search Results ==="]
    for i, r in enumerate(parser.results[:max_results], 1):
        title = html_module.unescape(r["title"]).strip()
        snippet = html_module.unescape(r["snippet"]).strip()
        url_text = r["url"].strip()
        lines.append(f"\n[{i}] {title}")
        if url_text:
            lines.append(f"    {url_text}")
        if snippet:
            lines.append(f"    {snippet}")
    lines.append("=== End of Web Search Results ===")
    return "\n".join(lines)
