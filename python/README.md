# contextfetch

Python client for the [ContextFetch](https://contextfetch.dev) API: web search, pages as Markdown, extractive answers, research, crawl and site maps for AI agents.

- No dependencies: standard library only (`urllib`, `json`).
- Typed: ships `py.typed`; responses are `TypedDict`s.
- Python 3.9 or newer.

## Install

```bash
pip install contextfetch
```

## Quickstart

```python
from contextfetch import ContextFetch

client = ContextFetch()  # reads CONTEXTFETCH_API_KEY; with no key it uses the keyless tier

res = client.search("python asyncio timeout", num_results=5, highlights=True, pruned_context=True)
for r in res["results"]:
    print(r["url"], r.get("title"))
    print(r.get("prunedContext", "")[:300])

page = client.read("https://docs.python.org/3/library/asyncio-task.html", query="task groups")
print(page.markdown)
```

No key yet? Get a free starter key (one per network, no signup):

```python
key = ContextFetch().free_key()["apiKey"]
client = ContextFetch(key)
```

## Methods

| Method | Endpoint |
|---|---|
| `search(query, *, num_results, include_domains, exclude_domains, start_published_date, text, highlights, pruned_context)` | `POST /v1/search` |
| `find_similar(url, *, ...same options as search)` | `POST /v1/findSimilar` |
| `contents(urls, *, text=True, highlights, pruned_context)` | `POST /v1/contents` |
| `answer(query, *, num_results, text)` | `POST /v1/answer` (extractive: passages quoted verbatim with `[n]` citations) |
| `research(query, *, sub_queries, num_results_per_query)` | `POST /v1/research` |
| `crawl(url, *, limit, max_depth, max_breadth, query, include_paths, exclude_paths)` | `POST /v1/crawl` |
| `map(url, *, limit, include_paths, exclude_paths)` | `POST /v1/map` |
| `read(url, *, query)` | `GET /r/{url}`, returns a `Page` (`markdown`, `raw_tokens`, `output_tokens`, `token_savings`) |
| `balance()` | `GET /v1/balance` |
| `free_key()` | `POST /v1/keys/free` |

`text`, `highlights` and `pruned_context` take `True` or an options object as described in the [API reference](https://contextfetch.dev/docs/reference), for example `highlights={"query": "task groups", "highlightsPerUrl": 2}`. Responses are the API's JSON as dicts, with the API's field names (`publishedDate`, `prunedContext`, ...).

Options: `ContextFetch(api_key=None, *, base_url="https://api.contextfetch.dev", timeout=60.0)`.

## Errors

Every error is a `ContextFetchError` with `status`, `code` (the body's `error` field) and `body`.

- `AuthenticationError`: HTTP 401, the key is not recognised.
- `PaymentRequiredError`: HTTP 402, credits or the keyless allowance ran out. `payment_url` is a one-click checkout link and `prompt_to_user` is a sentence to show your user; stop retrying until they pay.
- `APIConnectionError`: no response (DNS, connection or timeout).

```python
from contextfetch import ContextFetch, PaymentRequiredError

try:
    ContextFetch().search("rust async runtimes")
except PaymentRequiredError as e:
    print(e.prompt_to_user)  # includes e.payment_url
```

## Development

```bash
python -m unittest discover tests                                       # unit tests, local fake server
CONTEXTFETCH_API_KEY=... python -m unittest tests.test_live -v          # live smoke test, a few credits
```

## License

MIT
