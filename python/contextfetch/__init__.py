"""ContextFetch: web search and web pages as Markdown for AI agents.

A thin client for https://api.contextfetch.dev that uses only the Python standard library.
API reference: https://contextfetch.dev/docs/reference
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import Message
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union

__version__ = "0.1.0"

__all__ = [
    "APIConnectionError",
    "AnswerResponse",
    "AuthenticationError",
    "Balance",
    "ContentsResponse",
    "ContextFetch",
    "ContextFetchError",
    "CrawlResponse",
    "DEFAULT_BASE_URL",
    "FreeKey",
    "MapResponse",
    "Page",
    "PaymentRequiredError",
    "ResearchResponse",
    "Result",
    "SearchResponse",
]

DEFAULT_BASE_URL = "https://api.contextfetch.dev"

# A contents option: True, or an options object as the API reference describes it,
# e.g. highlights={"query": "task groups", "highlightsPerUrl": 2}.
Option = Union[bool, Dict[str, Any]]


# ---- responses (JSON as the API returns it; every key is optional) ----


class Result(TypedDict, total=False):
    id: str
    url: str
    title: Optional[str]
    score: Optional[float]
    publishedDate: Optional[str]
    author: Optional[str]
    text: str  # the page as Markdown
    highlights: List[str]
    highlightScores: List[float]
    prunedContext: str
    subQueries: List[str]  # research: the sub-queries that found this page
    depth: int  # crawl: link hops from the start URL


class SearchResponse(TypedDict, total=False):
    requestId: str
    results: List[Result]
    costDollars: Dict[str, float]
    searchTimeMs: float
    contextfetch: Dict[str, Any]  # cache, timingsMs, tokens, sources
    notice: str


class ContentsResponse(SearchResponse, total=False):
    statuses: List[Dict[str, Any]]  # one per URL: {"id", "status": "success" | "error", "error"?}


class ResearchResponse(SearchResponse, total=False):
    query: str
    subQueries: List[Dict[str, Any]]  # {"query", "status", "results"}
    evidence: str  # one Markdown document with numbered [n] sources quoted verbatim


class CrawlResponse(SearchResponse, total=False):
    baseUrl: str


class Citation(TypedDict, total=False):
    id: str
    url: str
    title: Optional[str]
    publishedDate: Optional[str]
    author: Optional[str]
    text: str


class Passage(TypedDict, total=False):
    text: str
    score: float
    citation: int  # 1-based index into citations


class AnswerResponse(TypedDict, total=False):
    answer: str  # passages quoted verbatim, each followed by [n]; "" when nothing is relevant enough
    type: str  # always "extractive"
    note: str
    citations: List[Citation]
    passages: List[Passage]
    costDollars: Dict[str, float]
    contextfetch: Dict[str, Any]
    notice: str


class MapResponse(TypedDict, total=False):
    requestId: str
    baseUrl: str
    results: List[str]
    costDollars: Dict[str, float]
    contextfetch: Dict[str, Any]
    notice: str


class Balance(TypedDict, total=False):
    credits: int
    auto_reload: Dict[str, Any]
    burn_rate_per_day: float


class FreeKey(TypedDict, total=False):
    apiKey: str
    credits: int
    buy: Dict[str, str]  # pack id -> checkout link


@dataclass(frozen=True)
class Page:
    """A page read through GET /r/{url}."""

    url: str
    markdown: str
    raw_tokens: Optional[int] = None  # X-Raw-Tokens
    output_tokens: Optional[int] = None  # X-Output-Tokens
    token_savings: Optional[float] = None  # X-Token-Savings, percent


# ---- errors ----


class ContextFetchError(Exception):
    """An API or transport error.

    status is the HTTP status (None when no response arrived), code the body's "error" field
    (e.g. "invalid_api_key", "recall_unavailable") and body the parsed JSON body, if any.
    """

    def __init__(self, message: str, status: Optional[int] = None, code: Optional[str] = None, body: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.body = body


class AuthenticationError(ContextFetchError):
    """HTTP 401: the API key is not recognised."""


class PaymentRequiredError(ContextFetchError):
    """HTTP 402: the key's credits or the keyless daily allowance ran out.

    Show prompt_to_user to your human and stop retrying. payment_url (the X-Payment-URL header)
    opens Stripe Checkout in one click; packs lists every pack with its own checkout_url.
    """

    def __init__(
        self,
        message: str,
        status: Optional[int] = None,
        code: Optional[str] = None,
        body: Any = None,
        payment_url: Optional[str] = None,
        prompt_to_user: Optional[str] = None,
    ) -> None:
        super().__init__(message, status, code, body)
        self.payment_url = payment_url
        self.prompt_to_user = prompt_to_user
        self.packs: List[Dict[str, Any]] = (body.get("packs") or []) if isinstance(body, dict) else []


class APIConnectionError(ContextFetchError):
    """No HTTP response: DNS, connection or timeout failure."""


# ---- client ----


class ContextFetch:
    """Client for the ContextFetch API.

    api_key defaults to the CONTEXTFETCH_API_KEY environment variable. With no key the client uses the
    keyless tier (a small daily allowance per IP); free_key() returns a starter key with no signup.
    """

    def __init__(self, api_key: Optional[str] = None, *, base_url: str = DEFAULT_BASE_URL, timeout: float = 60.0) -> None:
        self.api_key = (api_key if api_key is not None else os.environ.get("CONTEXTFETCH_API_KEY")) or None
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search(
        self,
        query: str,
        *,
        num_results: Optional[int] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        start_published_date: Optional[str] = None,
        text: Option = False,
        highlights: Option = False,
        pruned_context: Option = False,
    ) -> SearchResponse:
        """POST /v1/search. Results carry page text, highlights or prunedContext only when asked for."""
        body = {
            "query": query,
            "numResults": num_results,
            "includeDomains": include_domains,
            "excludeDomains": exclude_domains,
            "startPublishedDate": start_published_date,
            "contents": _contents(text, highlights, pruned_context),
        }
        return self._post("/v1/search", body)  # type: ignore[return-value]

    def find_similar(
        self,
        url: str,
        *,
        num_results: Optional[int] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        start_published_date: Optional[str] = None,
        text: Option = False,
        highlights: Option = False,
        pruned_context: Option = False,
    ) -> SearchResponse:
        """POST /v1/findSimilar: pages like url, from other domains. Same shape as search()."""
        body = {
            "url": url,
            "numResults": num_results,
            "includeDomains": include_domains,
            "excludeDomains": exclude_domains,
            "startPublishedDate": start_published_date,
            "contents": _contents(text, highlights, pruned_context),
        }
        return self._post("/v1/findSimilar", body)  # type: ignore[return-value]

    def contents(
        self,
        urls: List[str],
        *,
        text: Option = True,
        highlights: Option = False,
        pruned_context: Option = False,
    ) -> ContentsResponse:
        """POST /v1/contents: pages as Markdown. URLs that fail come back in statuses and are not billed."""
        body = {"urls": list(urls), "text": text, "highlights": highlights or None, "pruned_context": pruned_context or None}
        return self._post("/v1/contents", body)  # type: ignore[return-value]

    def answer(self, query: str, *, num_results: Optional[int] = None, text: bool = False) -> AnswerResponse:
        """POST /v1/answer: an extractive answer, passages quoted verbatim with [n] citations. Nothing is generated."""
        return self._post("/v1/answer", {"query": query, "numResults": num_results, "text": text or None})  # type: ignore[return-value]

    def research(
        self,
        query: str,
        *,
        sub_queries: Optional[List[str]] = None,
        num_results_per_query: Optional[int] = None,
    ) -> ResearchResponse:
        """POST /v1/research: several searches in one call, ranked together into an evidence pack."""
        body = {"query": query, "subQueries": sub_queries, "numResultsPerQuery": num_results_per_query}
        return self._post("/v1/research", body)  # type: ignore[return-value]

    def crawl(
        self,
        url: str,
        *,
        limit: Optional[int] = None,
        max_depth: Optional[int] = None,
        max_breadth: Optional[int] = None,
        query: Optional[str] = None,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
    ) -> CrawlResponse:
        """POST /v1/crawl: one site from a start URL, every page as Markdown. robots.txt is obeyed."""
        body = {
            "url": url,
            "limit": limit,
            "maxDepth": max_depth,
            "maxBreadth": max_breadth,
            "query": query,
            "includePaths": include_paths,
            "excludePaths": exclude_paths,
        }
        return self._post("/v1/crawl", body)  # type: ignore[return-value]

    def map(
        self,
        url: str,
        *,
        limit: Optional[int] = None,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
    ) -> MapResponse:
        """POST /v1/map: a site's URLs from its links and sitemaps, without fetching the pages."""
        body = {"url": url, "limit": limit, "includePaths": include_paths, "excludePaths": exclude_paths}
        return self._post("/v1/map", body)  # type: ignore[return-value]

    def read(self, url: str, *, query: Optional[str] = None) -> Page:
        """GET /r/{url}: any public URL as Markdown. With query, only the chunks relevant to it."""
        target = urllib.parse.urldefrag(url)[0]
        path = "/r/" + urllib.parse.quote(target, safe=":/?&=%@+,;~!$'()*[]")
        if query:
            path += ("&" if "?" in target else "?") + urllib.parse.urlencode({"q": query})
        raw, headers = self._request("GET", path)
        return Page(
            url=target,
            markdown=raw.decode("utf-8", "replace"),
            raw_tokens=_number(headers.get("X-Raw-Tokens"), int),
            output_tokens=_number(headers.get("X-Output-Tokens"), int),
            token_savings=_number(headers.get("X-Token-Savings"), float),
        )

    def balance(self) -> Balance:
        """GET /v1/balance: credits left on this key and its auto-reload settings. Free."""
        return _json(self._request("GET", "/v1/balance")[0])  # type: ignore[return-value]

    def free_key(self) -> FreeKey:
        """POST /v1/keys/free: a free starter key, one per network. Sent without this client's key."""
        return _json(self._request("POST", "/v1/keys/free", auth=False)[0])  # type: ignore[return-value]

    # ---- transport ----

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return _json(self._request("POST", path, {k: v for k, v in body.items() if v is not None})[0])

    def _request(
        self, method: str, path: str, body: Optional[Dict[str, Any]] = None, auth: bool = True
    ) -> Tuple[bytes, Message]:
        headers = {"User-Agent": f"contextfetch-python/{__version__}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return res.read(), res.headers
        except urllib.error.HTTPError as e:
            raise _api_error(e.code, e.read(), e.headers) from None
        except (urllib.error.URLError, OSError) as e:  # OSError covers timeouts
            reason = getattr(e, "reason", None) or e
            raise APIConnectionError(f"Could not reach the ContextFetch API at {self.base_url}: {reason}") from e


def _contents(text: Option, highlights: Option, pruned_context: Option) -> Optional[Dict[str, Option]]:
    wanted = {"text": text, "highlights": highlights, "pruned_context": pruned_context}
    return {k: v for k, v in wanted.items() if v} or None


def _json(raw: bytes) -> Dict[str, Any]:
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise ContextFetchError(f"The ContextFetch API returned an unreadable response: {raw[:200]!r}")
    return data


def _number(value: Optional[str], kind: Any) -> Any:
    try:
        return kind(value) if value is not None else None
    except ValueError:
        return None


def _api_error(status: int, raw: bytes, headers: Message) -> ContextFetchError:
    try:
        body: Any = json.loads(raw)
    except ValueError:
        body = None
    info: Dict[str, Any] = body if isinstance(body, dict) else {}
    code = info.get("error") if isinstance(info.get("error"), str) else None
    detail = info.get("message") or info.get("detail") or code or raw.decode("utf-8", "replace")[:300]
    if not isinstance(detail, str):
        detail = json.dumps(detail)[:300]
    message = f"ContextFetch API returned HTTP {status}" + (f" ({code})" if code else "") + (f": {detail}" if detail and detail != code else "")
    if status == 401:
        return AuthenticationError(message, status, code, body)
    if status == 402:
        action: Dict[str, Any] = info["action"] if isinstance(info.get("action"), dict) else {}
        prompt = action.get("prompt_to_user")
        if prompt and prompt not in message:
            message += f" {prompt}"
        return PaymentRequiredError(message, status, code, body, headers.get("X-Payment-URL") or action.get("url"), prompt)
    return ContextFetchError(message, status, code, body)
