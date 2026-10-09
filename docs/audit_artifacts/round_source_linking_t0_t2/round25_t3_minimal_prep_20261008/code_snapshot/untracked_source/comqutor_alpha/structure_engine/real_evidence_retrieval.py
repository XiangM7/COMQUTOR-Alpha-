"""Real search + real webpage retrieval for supplementary evidence (T1 v3
spec, section 三 point 4; 2026-10-06).

Two genuinely separate capabilities, deliberately not conflated:

  1. **Search** (query -> candidate URLs/snippets): requires a real,
     configured external search provider. As of this module's own creation
     date, NO search API credential exists anywhere in this project's real
     ``.env`` (checked directly, not assumed) -- there is therefore
     currently NO way for this module to perform a real search. Rather than
     fake this with an empty-implementation stub that silently "succeeds"
     with zero results (which a caller could easily misread as "searched,
     found nothing" instead of "search was never actually possible"),
     :func:`resolve_search_provider` returns a provider whose own
     ``search()`` raises :class:`SearchProviderUnavailable` with a specific,
     stable reason code. A real provider (Tavily, Bing, SerpAPI, ...) can be
     wired in later by adding one class here implementing the
     :class:`SearchProvider` protocol and extending
     :func:`resolve_search_provider`'s own env-var resolution -- deliberately
     NOT done in this round, per explicit instruction to hold off until a
     provider is chosen and provisioned.

  2. **Fetch + extract** (URL -> real, locatable text content): requires no
     special credential, just real network access -- genuinely implemented
     in this module using ``requests`` (already a project dependency) and
     BeautifulSoup/lxml (already present in this project's real virtualenv,
     confirmed directly before writing this module, not assumed) for HTML
     text extraction. This half is real today, not a stub.

Both halves report every real outcome (success, timeout, HTTP error, empty
content, non-HTML content) as a distinct, named status -- never silently
converted into "no evidence found" or a fabricated success.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import requests

# --- shared status vocabulary -----------------------------------------------

STATUS_OK = "OK"
STATUS_PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_HTTP_ERROR = "HTTP_ERROR"
STATUS_CONTENT_EMPTY = "CONTENT_EMPTY"
STATUS_NOT_TEXTUAL_CONTENT = "NOT_TEXTUAL_CONTENT"
STATUS_NETWORK_ERROR = "NETWORK_ERROR"
STATUS_URL_INVALID = "URL_INVALID"

VALID_RETRIEVAL_STATUSES = frozenset(
    {
        STATUS_OK,
        STATUS_PROVIDER_UNAVAILABLE,
        STATUS_TIMEOUT,
        STATUS_HTTP_ERROR,
        STATUS_CONTENT_EMPTY,
        STATUS_NOT_TEXTUAL_CONTENT,
        STATUS_NETWORK_ERROR,
        STATUS_URL_INVALID,
    }
)


class SearchProviderUnavailable(Exception):
    """Raised by a SearchProvider.search() call when no real search backend
    is configured/reachable. Carries a stable ``reason_code`` -- never a
    bare exception message a caller would have to pattern-match."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


@dataclass(frozen=True)
class SearchResultItem:
    """One real result from a real search provider. ``snippet`` is the
    provider's own returned summary text, shown to a caller for triage only
    -- it is NEVER treated as evidence content on its own (section 三's own
    explicit requirement: "搜索标题、摘要...不能替代证据"). Evidence content
    only exists after :func:`fetch_and_extract_url` actually reads the page."""

    query: str
    url: str
    title: str
    snippet: str
    rank: int
    provider: str
    retrieved_at: str


class SearchProvider(Protocol):
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResultItem]: ...

    @property
    def provider_name(self) -> str: ...


class _NoSearchProviderConfigured:
    """Honest, explicit stand-in -- never returns an empty result list
    (which would be indistinguishable from "searched, found nothing").
    Every call raises, naming exactly why."""

    provider_name = "none_configured"

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResultItem]:
        raise SearchProviderUnavailable(
            "SEARCH_PROVIDER_NOT_CONFIGURED",
            "No real search API credential is configured in this environment "
            "(checked TAVILY_API_KEY/BING_SEARCH_API_KEY/SERPAPI_API_KEY -- none present). "
            "Real search cannot run until a provider is chosen and its credential is added.",
        )


def resolve_search_provider() -> SearchProvider:
    """Reads real environment variables for a configured search provider.
    Returns :class:`_NoSearchProviderConfigured` (whose own ``search()``
    always raises :class:`SearchProviderUnavailable`) when none is found --
    this is the current, real, honest state of this environment, confirmed
    by directly reading .env before this module was written, not assumed.

    Extend this function (never fake a provider's own search() body) when a
    real provider is provisioned -- e.g.:
        if os.environ.get("TAVILY_API_KEY"):
            return _TavilySearchProvider(os.environ["TAVILY_API_KEY"])
    """
    import os

    if os.environ.get("TAVILY_API_KEY"):
        raise NotImplementedError(
            "TAVILY_API_KEY is set, but no _TavilySearchProvider implementation exists yet in "
            "this module -- add one here rather than silently falling through to "
            "_NoSearchProviderConfigured, which would hide a real, available credential."
        )
    if os.environ.get("BING_SEARCH_API_KEY"):
        raise NotImplementedError(
            "BING_SEARCH_API_KEY is set, but no Bing provider implementation exists yet."
        )
    if os.environ.get("SERPAPI_API_KEY"):
        raise NotImplementedError(
            "SERPAPI_API_KEY is set, but no SerpAPI provider implementation exists yet."
        )
    return _NoSearchProviderConfigured()


# --- real webpage fetch + extraction (no credential required) --------------

DEFAULT_FETCH_TIMEOUT_SECONDS = 15.0
DEFAULT_USER_AGENT = "COMQUTOR-Alpha-Research/1.0 (+evidence-retrieval)"
MAX_EXTRACTED_TEXT_CHARS = 20_000


@dataclass(frozen=True)
class FetchedPage:
    """The real, saved result of attempting to fetch and extract one real
    URL. ``extracted_text`` is empty exactly when ``status`` is not
    :data:`STATUS_OK` -- never a partial/best-effort value on failure.
    ``content_hash`` is computed over ``extracted_text`` (not the raw HTML),
    so content-identity checks downstream compare what was actually handed
    to a verification model, not raw markup."""

    url: str
    status: str
    http_status_code: int | None
    content_type: str | None
    title: str
    extracted_text: str
    content_hash: str | None
    retrieved_at: str
    error_detail: str | None = field(default=None)


def _looks_like_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value.strip(), re.IGNORECASE))


def _extract_readable_text(html: str) -> tuple[str, str]:
    """Real HTML text extraction via BeautifulSoup/lxml (both confirmed
    present in this project's real virtualenv before this module was
    written -- not a new, unapproved dependency). Strips script/style/nav/
    footer/header/aside boilerplate tags, collapses whitespace. Returns
    (title, body_text). Never invents content when the page has none --
    returns ("", "") for a page with no extractable text."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
        tag.decompose()
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    body = soup.body or soup
    text = body.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    non_empty = [line for line in lines if line]
    joined = "\n".join(non_empty)
    return title, joined[:MAX_EXTRACTED_TEXT_CHARS]


def fetch_and_extract_url(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    session: Any = None,
) -> FetchedPage:
    """Real, synchronous HTTP GET of ``url`` with real text extraction.
    Every failure mode is a distinct, honestly-recorded status -- never
    silently converted into empty-but-successful content. Never follows
    more than ``requests``' own default safe redirect handling; never
    executes any script on the page (BeautifulSoup/lxml parse markup only,
    no JS execution -- a JS-rendered page may legitimately come back with
    little/no extractable text, reported as STATUS_CONTENT_EMPTY, not
    silently papered over)."""
    now = datetime.now(timezone.utc).isoformat()
    if not _looks_like_url(url):
        return FetchedPage(
            url=url,
            status=STATUS_URL_INVALID,
            http_status_code=None,
            content_type=None,
            title="",
            extracted_text="",
            content_hash=None,
            retrieved_at=now,
            error_detail="URL does not start with http:// or https://",
        )

    client = session or requests
    try:
        response = client.get(
            url,
            timeout=timeout_seconds,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        )
    except requests.exceptions.Timeout:
        return FetchedPage(
            url=url, status=STATUS_TIMEOUT, http_status_code=None, content_type=None,
            title="", extracted_text="", content_hash=None, retrieved_at=now,
            error_detail=f"request timed out after {timeout_seconds}s",
        )
    except requests.exceptions.RequestException as exc:
        return FetchedPage(
            url=url, status=STATUS_NETWORK_ERROR, http_status_code=None, content_type=None,
            title="", extracted_text="", content_hash=None, retrieved_at=now,
            error_detail=f"{type(exc).__name__}: {exc}",
        )

    if response.status_code >= 400:
        return FetchedPage(
            url=url, status=STATUS_HTTP_ERROR, http_status_code=response.status_code,
            content_type=response.headers.get("content-type"), title="", extracted_text="",
            content_hash=None, retrieved_at=now,
            error_detail=f"HTTP {response.status_code}",
        )

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower() and not content_type.lower().startswith("text/"):
        return FetchedPage(
            url=url, status=STATUS_NOT_TEXTUAL_CONTENT, http_status_code=response.status_code,
            content_type=content_type, title="", extracted_text="", content_hash=None,
            retrieved_at=now, error_detail=f"content-type={content_type!r} is not html/text",
        )

    title, text = _extract_readable_text(response.text)
    if not text.strip():
        return FetchedPage(
            url=url, status=STATUS_CONTENT_EMPTY, http_status_code=response.status_code,
            content_type=content_type, title=title, extracted_text="", content_hash=None,
            retrieved_at=now, error_detail="page fetched successfully but no extractable text remained",
        )

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return FetchedPage(
        url=url, status=STATUS_OK, http_status_code=response.status_code,
        content_type=content_type, title=title, extracted_text=text,
        content_hash=content_hash, retrieved_at=now, error_detail=None,
    )
