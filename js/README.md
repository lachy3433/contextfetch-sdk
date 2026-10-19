# @contextfetch/sdk

TypeScript client for the [ContextFetch](https://contextfetch.dev) API: web search, pages as Markdown, extractive answers, research, crawl and site maps for AI agents.

- No dependencies: uses the global `fetch`.
- Types included (`dist/index.d.ts`).
- ESM, Node.js 18 or newer.

## Install

```bash
npm install @contextfetch/sdk
```

## Quickstart

```ts
import { ContextFetch } from "@contextfetch/sdk";

const client = new ContextFetch(); // reads CONTEXTFETCH_API_KEY; with no key it uses the keyless tier

const res = await client.search("python asyncio timeout", { numResults: 5, highlights: true, prunedContext: true });
for (const r of res.results) console.log(r.url, r.title, r.prunedContext?.slice(0, 300));

const page = await client.read("https://docs.python.org/3/library/asyncio-task.html", { query: "task groups" });
console.log(page.markdown);
```

No key yet? Get a free starter key (one per network, no signup):

```ts
const { apiKey } = await new ContextFetch().freeKey();
const client = new ContextFetch(apiKey);
```

## Methods

| Method | Endpoint |
|---|---|
| `search(query, { numResults, includeDomains, excludeDomains, startPublishedDate, text, highlights, prunedContext })` | `POST /v1/search` |
| `findSimilar(url, { ...same options as search })` | `POST /v1/findSimilar` |
| `contents(urls, { text = true, highlights, prunedContext })` | `POST /v1/contents` |
| `answer(query, { numResults, text })` | `POST /v1/answer` (extractive: passages quoted verbatim with `[n]` citations) |
| `research(query, { subQueries, numResultsPerQuery })` | `POST /v1/research` |
| `crawl(url, { limit, maxDepth, maxBreadth, query, includePaths, excludePaths })` | `POST /v1/crawl` |
| `map(url, { limit, includePaths, excludePaths })` | `POST /v1/map` |
| `read(url, { query })` | `GET /r/{url}`, returns a `Page` (`markdown`, `rawTokens`, `outputTokens`, `tokenSavings`) |
| `balance()` | `GET /v1/balance` |
| `freeKey()` | `POST /v1/keys/free` |

`text`, `highlights` and `prunedContext` take `true` or an options object as described in the [API reference](https://contextfetch.dev/docs/reference), for example `highlights: { query: "task groups", highlightsPerUrl: 2 }`. Responses are the API's JSON with the API's field names.

Options: `new ContextFetch(apiKey?, { baseUrl = "https://api.contextfetch.dev", timeoutMs = 60000 })`.

## Errors

Every error is a `ContextFetchError` with `status`, `code` (the body's `error` field) and `body`.

- `AuthenticationError`: HTTP 401, the key is not recognised.
- `PaymentRequiredError`: HTTP 402, credits or the keyless allowance ran out. `paymentUrl` is a one-click checkout link and `promptToUser` is a sentence to show your user; stop retrying until they pay.
- `APIConnectionError`: no response (DNS, connection or timeout).

```ts
import { ContextFetch, PaymentRequiredError } from "@contextfetch/sdk";

try {
  await new ContextFetch().search("rust async runtimes");
} catch (e) {
  if (e instanceof PaymentRequiredError) console.log(e.promptToUser); // includes e.paymentUrl
  else throw e;
}
```

## Development

```bash
npm install
npm test                                        # builds, then unit tests against a local fake server
CONTEXTFETCH_API_KEY=... node --test test/live.test.mjs   # live smoke test, a few credits (run npm run build first)
```

## License

MIT
