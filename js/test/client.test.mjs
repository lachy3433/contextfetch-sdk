// Unit tests against a local fake of the API (node:http). No network.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { after, before, beforeEach, test } from "node:test";

import { APIConnectionError, AuthenticationError, ContextFetch, ContextFetchError, PaymentRequiredError } from "../dist/index.js";

const PAY_URL = "https://api.contextfetch.dev/buy/instant";
const PAYMENT_BODY = {
  error: "insufficient_credits",
  message: "This key is out of credits.",
  checkout_url: "https://contextfetch.dev/#buy",
  packs: [{ id: "instant", credits: 1000, checkout_url: PAY_URL }],
  action: { type: "payment_link", url: PAY_URL, prompt_to_user: `ContextFetch credits ran out: ${PAY_URL}` },
};

let server, base, requests, reply, client;

before(async () => {
  server = createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      requests.push({ method: req.method, path: req.url, headers: req.headers, body: raw ? JSON.parse(raw) : null });
      const [status, headers, payload] = reply;
      const data = typeof payload === "string" ? payload : JSON.stringify(payload);
      res.writeHead(status, headers);
      res.end(data);
    });
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  base = `http://127.0.0.1:${server.address().port}`;
});

after(() => server.close());

beforeEach(() => {
  requests = [];
  reply = [200, { "content-type": "application/json" }, { results: [] }];
  client = new ContextFetch("cf_live_test", { baseUrl: base + "/" });
});

const last = () => requests.at(-1);

test("search sends the key and a camelCase body", async () => {
  reply = [200, {}, { requestId: "r1", results: [{ url: "https://a.example", text: "# A" }] }];
  const out = await client.search("vector databases", { numResults: 3, excludeDomains: ["pinterest.com"], text: true, prunedContext: true });
  assert.equal(out.results[0].text, "# A");
  assert.equal(last().method, "POST");
  assert.equal(last().path, "/v1/search");
  assert.equal(last().headers.authorization, "Bearer cf_live_test");
  assert.match(last().headers["user-agent"], /^contextfetch-js\//);
  assert.deepEqual(last().body, {
    query: "vector databases",
    numResults: 3,
    excludeDomains: ["pinterest.com"],
    contents: { text: true, pruned_context: true },
  });
});

test("search without contents omits it", async () => {
  await client.search("q");
  assert.deepEqual(last().body, { query: "q" });
});

test("endpoint paths and bodies", async () => {
  const cases = [
    [() => client.findSimilar("https://a.example", { numResults: 2, highlights: { query: "x" } }), "/v1/findSimilar",
      { url: "https://a.example", numResults: 2, contents: { highlights: { query: "x" } } }],
    [() => client.contents(["https://a.example"]), "/v1/contents", { urls: ["https://a.example"], text: true }],
    [() => client.contents(["https://a.example"], { text: false, highlights: true }), "/v1/contents",
      { urls: ["https://a.example"], text: false, highlights: true }],
    [() => client.answer("why?", { numResults: 4, text: true }), "/v1/answer", { query: "why?", numResults: 4, text: true }],
    [() => client.research("topic", { subQueries: ["a", "b"], numResultsPerQuery: 2 }), "/v1/research",
      { query: "topic", subQueries: ["a", "b"], numResultsPerQuery: 2 }],
    [() => client.crawl("https://a.example", { limit: 5, maxDepth: 2, query: "t", includePaths: ["/docs"] }), "/v1/crawl",
      { url: "https://a.example", limit: 5, maxDepth: 2, query: "t", includePaths: ["/docs"] }],
    [() => client.map("https://a.example", { limit: 50, excludePaths: ["/blog"] }), "/v1/map",
      { url: "https://a.example", limit: 50, excludePaths: ["/blog"] }],
  ];
  for (const [call, path, body] of cases) {
    await call();
    assert.deepEqual([last().method, last().path, last().body], ["POST", path, body]);
  }
});

test("balance is a GET with the key", async () => {
  reply = [200, {}, { credits: 2499, auto_reload: { enabled: false }, burn_rate_per_day: 1 }];
  assert.equal((await client.balance()).credits, 2499);
  assert.deepEqual([last().method, last().path, last().body], ["GET", "/v1/balance", null]);
  assert.equal(last().headers.authorization, "Bearer cf_live_test");
});

test("freeKey is sent without a key", async () => {
  reply = [201, {}, { apiKey: "cf_live_" + "0".repeat(32), credits: 2500 }];
  assert.equal((await client.freeKey()).credits, 2500);
  assert.deepEqual([last().method, last().path], ["POST", "/v1/keys/free"]);
  assert.equal(last().headers.authorization, undefined);
});

test("keyless when no key anywhere, env key otherwise", async () => {
  const saved = process.env.CONTEXTFETCH_API_KEY;
  try {
    delete process.env.CONTEXTFETCH_API_KEY;
    await new ContextFetch(undefined, { baseUrl: base }).search("q");
    assert.equal(last().headers.authorization, undefined);
    process.env.CONTEXTFETCH_API_KEY = "cf_live_env";
    await new ContextFetch(undefined, { baseUrl: base }).search("q");
    assert.equal(last().headers.authorization, "Bearer cf_live_env");
  } finally {
    if (saved === undefined) delete process.env.CONTEXTFETCH_API_KEY;
    else process.env.CONTEXTFETCH_API_KEY = saved;
  }
});

test("read returns Markdown and the token headers", async () => {
  reply = [200, { "content-type": "text/markdown; charset=utf-8", "x-token-savings": "91.0", "x-raw-tokens": "18240", "x-output-tokens": "1650" }, "## Task Groups\n\nÜnïcode"];
  const page = await client.read("https://docs.python.org/3/library/asyncio-task.html#frag", { query: "task groups" });
  assert.deepEqual(page, {
    url: "https://docs.python.org/3/library/asyncio-task.html",
    markdown: "## Task Groups\n\nÜnïcode",
    rawTokens: 18240,
    outputTokens: 1650,
    tokenSavings: 91,
  });
  assert.equal(last().path, "/r/https://docs.python.org/3/library/asyncio-task.html?q=task+groups");
});

test("read keeps the target's query and encodes spaces", async () => {
  reply = [200, {}, "x"];
  const page = await client.read("https://a.example/a b?id=1", { query: "q" });
  assert.equal(last().path, "/r/https://a.example/a%20b?id=1&q=q");
  assert.equal(page.rawTokens, null);
});

test("402 exposes the payment link", async () => {
  reply = [402, { "x-payment-url": PAY_URL }, PAYMENT_BODY];
  const err = await client.search("q").catch((e) => e);
  assert.ok(err instanceof PaymentRequiredError && err instanceof ContextFetchError);
  assert.equal(err.name, "PaymentRequiredError");
  assert.deepEqual([err.status, err.code, err.paymentUrl], [402, "insufficient_credits", PAY_URL]);
  assert.equal(err.promptToUser, PAYMENT_BODY.action.prompt_to_user);
  assert.equal(err.packs[0].id, "instant");
  assert.match(err.message, /buy\/instant/);
});

test("402 without the header falls back to action.url", async () => {
  reply = [402, {}, PAYMENT_BODY];
  const err = await client.read("https://a.example").catch((e) => e);
  assert.equal(err.paymentUrl, PAY_URL);
});

test("401 is an AuthenticationError", async () => {
  reply = [401, {}, { error: "invalid_api_key" }];
  const err = await client.balance().catch((e) => e);
  assert.ok(err instanceof AuthenticationError);
  assert.deepEqual([err.status, err.code], [401, "invalid_api_key"]);
});

test("other errors carry status, code and message", async () => {
  reply = [503, {}, { error: "recall_unavailable", message: "Web search backends are down." }];
  const err = await client.search("q").catch((e) => e);
  assert.ok(err instanceof ContextFetchError && !(err instanceof PaymentRequiredError));
  assert.deepEqual([err.status, err.code], [503, "recall_unavailable"]);
  assert.match(err.message, /Web search backends are down\./);
});

test("validation error detail is in the message", async () => {
  reply = [422, {}, { detail: [{ loc: ["body", "query"], msg: "too long" }] }];
  const err = await client.search("q").catch((e) => e);
  assert.match(err.message, /too long/);
});

test("non-JSON error body", async () => {
  reply = [502, { "content-type": "text/html" }, "<html>Bad Gateway</html>"];
  const err = await client.search("q").catch((e) => e);
  assert.deepEqual([err.status, err.code, err.body], [502, null, null]);
  assert.match(err.message, /Bad Gateway/);
});

test("unreadable success body", async () => {
  reply = [200, {}, "not json"];
  await assert.rejects(client.search("q"), ContextFetchError);
});

test("connection failure", async () => {
  const closed = createServer();
  await new Promise((r) => closed.listen(0, "127.0.0.1", r));
  const port = closed.address().port;
  await new Promise((r) => closed.close(r));
  const err = await new ContextFetch("k", { baseUrl: `http://127.0.0.1:${port}` }).search("q").catch((e) => e);
  assert.ok(err instanceof APIConnectionError);
  assert.equal(err.status, null);
});
