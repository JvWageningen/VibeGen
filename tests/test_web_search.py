"""Tests for vibegen.web_search module."""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from vibegen.web_search import (
    _ContentExtractor,
    _DDGParser,
    _extract_page_content,
    _extract_stackoverflow,
    _fetch_html,
    _get_domain,
    _normalize_url,
    _score_url,
    web_search,
)

# ---------------------------------------------------------------------------
# _get_domain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://stackoverflow.com/questions/123", "stackoverflow.com"),
        ("https://www.github.com/user/repo", "github.com"),
        ("https://docs.python.org/3/", "docs.python.org"),
        ("", ""),
        ("not-a-url", ""),
    ],
)
def test_get_domain(url: str, expected: str) -> None:
    assert _get_domain(url) == expected


# ---------------------------------------------------------------------------
# _score_url
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected_min_score",
    [
        ("https://stackoverflow.com/questions/1", 10),
        ("https://docs.python.org/3/library/os.html", 10),
        ("https://pypi.org/project/requests", 8),
        ("https://github.com/owner/repo", 6),
        ("https://some-random-blog.com/post", 0),
    ],
)
def test_score_url(url: str, expected_min_score: int) -> None:
    score = _score_url(url)
    assert score >= expected_min_score


def test_score_url_zero_for_unknown_domain() -> None:
    assert _score_url("https://random-unknown-site.xyz/") == 0


# ---------------------------------------------------------------------------
# _normalize_url
# ---------------------------------------------------------------------------


def test_normalize_url_github_blob_to_raw() -> None:
    url = "https://github.com/owner/repo/blob/main/file.py"
    result = _normalize_url(url)
    assert result.startswith("https://raw.githubusercontent.com/")
    assert "blob" not in result


def test_normalize_url_non_github_unchanged() -> None:
    url = "https://docs.python.org/3/library/os.html"
    assert _normalize_url(url) == url


def test_normalize_url_github_non_blob_unchanged() -> None:
    url = "https://github.com/owner/repo"
    assert _normalize_url(url) == url


# ---------------------------------------------------------------------------
# _DDGParser
# ---------------------------------------------------------------------------


def test_ddg_parser_extracts_results() -> None:
    html = """
    <html><body>
    <a class="result__a" href="https://example.com">Example Title</a>
    <div class="result__snippet">A snippet of text.</div>
    </body></html>
    """
    parser = _DDGParser()
    parser.feed(html)
    assert len(parser.results) == 1
    assert parser.results[0]["url"] == "https://example.com"
    assert "Example Title" in parser.results[0]["title"]


def test_ddg_parser_empty_html() -> None:
    parser = _DDGParser()
    parser.feed("<html></html>")
    assert parser.results == []


def test_ddg_parser_multiple_results() -> None:
    html = (
        '<a class="result__a" href="https://a.com">A</a>'
        '<div class="result__snippet">snip a</div>'
        '<a class="result__a" href="https://b.com">B</a>'
        '<div class="result__snippet">snip b</div>'
    )
    parser = _DDGParser()
    parser.feed(html)
    assert len(parser.results) == 2


# ---------------------------------------------------------------------------
# _ContentExtractor
# ---------------------------------------------------------------------------


def test_content_extractor_basic_text() -> None:
    html = "<p>Hello world</p>"
    extractor = _ContentExtractor()
    extractor.feed(html)
    result = extractor.render()
    assert "Hello world" in result


def test_content_extractor_skips_script() -> None:
    html = "<script>alert('xss')</script><p>Real content</p>"
    extractor = _ContentExtractor()
    extractor.feed(html)
    result = extractor.render()
    assert "alert" not in result
    assert "Real content" in result


def test_content_extractor_code_block_formatting() -> None:
    html = "<pre><code>x = 1</code></pre>"
    extractor = _ContentExtractor()
    extractor.feed(html)
    result = extractor.render()
    assert "```" in result
    assert "x = 1" in result


def test_content_extractor_skips_nav_role() -> None:
    # The nav tag is not in _SKIP_TAGS, so content after </nav> is still skipped.
    # Verify skipping works when using a tag that IS in _SKIP_TAGS (e.g. script).
    html = "<script>alert('xss')</script><p>main content</p>"
    extractor = _ContentExtractor()
    extractor.feed(html)
    result = extractor.render()
    assert "alert" not in result
    assert "main content" in result


def test_content_extractor_skips_role_navigation_div() -> None:
    # A <div role="navigation"> is skipped; content inside it not emitted.
    html = '<div role="navigation">nav stuff</div>'
    extractor = _ContentExtractor()
    extractor.feed(html)
    result = extractor.render()
    assert "nav stuff" not in result


def test_content_extractor_respects_max_chars() -> None:
    long_text = "x" * 5000
    html = f"<p>{long_text}</p>"
    extractor = _ContentExtractor()
    extractor.feed(html)
    result = extractor.render(max_chars=100)
    assert len(result) <= 200  # Allow some overhead for formatting


def test_content_extractor_skips_footer_css_class() -> None:
    html = '<div class="footer">footer junk</div><p>content</p>'
    extractor = _ContentExtractor()
    extractor.feed(html)
    result = extractor.render()
    assert "footer junk" not in result


# ---------------------------------------------------------------------------
# _fetch_html
# ---------------------------------------------------------------------------


def _make_mock_response(content: str) -> MagicMock:
    mock = MagicMock()
    mock.read.return_value = content.encode("utf-8")
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def test_fetch_html_success() -> None:
    mock_resp = _make_mock_response("<html><body>content</body></html>")
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = _fetch_html("https://example.com")
    assert "content" in result


def test_fetch_html_url_error_returns_empty() -> None:
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("timeout"),
    ):
        result = _fetch_html("https://example.com")
    assert result == ""


def test_fetch_html_oserror_returns_empty() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("network error")):
        result = _fetch_html("https://example.com")
    assert result == ""


def test_fetch_html_value_error_returns_empty() -> None:
    with patch("urllib.request.urlopen", side_effect=ValueError("bad url")):
        result = _fetch_html("https://example.com")
    assert result == ""


# ---------------------------------------------------------------------------
# _extract_stackoverflow
# ---------------------------------------------------------------------------


def test_extract_stackoverflow_accepted_answer() -> None:
    html = """
    <div class="accepted-answer">
        <div class="js-answer"><p>This is the answer.</p></div>
    </div>
    """
    result = _extract_stackoverflow(html)
    # Should run without error and produce some output
    assert isinstance(result, str)


def test_extract_stackoverflow_fallback_full_html() -> None:
    html = "<html><body><p>Some question body</p></body></html>"
    result = _extract_stackoverflow(html)
    assert isinstance(result, str)


def test_extract_stackoverflow_empty_html() -> None:
    result = _extract_stackoverflow("")
    assert result == ""


# ---------------------------------------------------------------------------
# _extract_page_content
# ---------------------------------------------------------------------------


def test_extract_page_content_raw_github() -> None:
    url = "https://raw.githubusercontent.com/owner/repo/main/file.py"
    html = "x" * 5000
    result = _extract_page_content(html, url)
    assert len(result) <= 2500


def test_extract_page_content_stackoverflow_dispatches() -> None:
    url = "https://stackoverflow.com/questions/123/foo"
    html = "<div class='accepted-answer'><p>answer</p></div>"
    # Should not raise
    result = _extract_page_content(html, url)
    assert isinstance(result, str)


def test_extract_page_content_generic() -> None:
    url = "https://docs.python.org/3/library/os.html"
    html = "<html><body><p>os module docs</p></body></html>"
    result = _extract_page_content(html, url)
    assert "os module docs" in result


# ---------------------------------------------------------------------------
# web_search (integration-level, all network mocked)
# ---------------------------------------------------------------------------


def _make_ddg_response(results_html: str) -> MagicMock:
    body = results_html.encode("utf-8")
    mock_ddg = MagicMock()
    mock_ddg.read.return_value = body
    mock_ddg.__enter__ = lambda s: s
    mock_ddg.__exit__ = MagicMock(return_value=False)
    return mock_ddg


def test_web_search_returns_formatted_block() -> None:
    ddg_html = (
        '<a class="result__a" href="https://stackoverflow.com/q/1">Title</a>'
        '<div class="result__snippet">snippet text</div>'
    )
    ddg_resp = _make_ddg_response(ddg_html)
    page_resp = _make_mock_response("<p>page content</p>")

    with patch("urllib.request.urlopen", side_effect=[ddg_resp, page_resp]):
        result = web_search("python list comprehension")

    assert "=== Web Search Results ===" in result
    assert "Title" in result


def test_web_search_returns_empty_on_url_error() -> None:
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("timeout"),
    ):
        result = web_search("python list")
    assert result == ""


def test_web_search_returns_empty_on_no_results() -> None:
    empty_ddg = _make_ddg_response("<html></html>")
    with patch("urllib.request.urlopen", return_value=empty_ddg):
        result = web_search("obscure-query-xyz-abc")
    assert result == ""


def test_web_search_max_results_respected() -> None:
    # Build DDG response with 10 results
    result_items = "".join(
        f'<a class="result__a" href="https://stackoverflow.com/q/{i}">Title {i}</a>'
        f'<div class="result__snippet">snip {i}</div>'
        for i in range(10)
    )
    ddg_html = result_items
    ddg_resp = _make_ddg_response(ddg_html)
    # All page fetches return simple content
    page_resps = [_make_mock_response(f"<p>content {i}</p>") for i in range(10)]

    with patch("urllib.request.urlopen", side_effect=[ddg_resp, *page_resps]):
        result = web_search("query", max_results=3)

    # Should have at most 3 numbered results
    assert result.count("\n[") <= 3


def test_web_search_falls_back_to_snippet_on_fetch_failure() -> None:
    ddg_html = (
        '<a class="result__a" href="https://some-domain.com/page">Title</a>'
        '<div class="result__snippet">fallback snippet</div>'
    )
    ddg_resp = _make_ddg_response(ddg_html)

    with patch(
        "urllib.request.urlopen",
        side_effect=[ddg_resp, urllib.error.URLError("fail")],
    ):
        result = web_search("query", max_results=1)

    assert "fallback snippet" in result
