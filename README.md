# ContextFetch SDKs

Thin, zero-dependency clients for the [ContextFetch](https://contextfetch.dev) API: web search and any page as
LLM-ready Markdown for AI agents.

| Language | Package | Source |
| --- | --- | --- |
| Python (stdlib HTTP, typed) | [`contextfetch`](https://pypi.org/project/contextfetch/) | [`python/`](python) |
| JavaScript / TypeScript | [`@contextfetch/sdk`](https://www.npmjs.com/package/@contextfetch/sdk) | [`js/`](js) |

```bash
pip install contextfetch
npm install @contextfetch/sdk
```

Both work without a key on the free tier (25 requests a day per IP); set `CONTEXTFETCH_API_KEY` for more.
API reference: https://contextfetch.dev/docs/reference. MIT licensed.
