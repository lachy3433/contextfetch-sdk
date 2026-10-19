// Live smoke test against the real API. Runs only when CONTEXTFETCH_API_KEY is set; uses about 3 credits.
import assert from "node:assert/strict";
import { test } from "node:test";

import { ContextFetch } from "../dist/index.js";

const skip = !process.env.CONTEXTFETCH_API_KEY && "CONTEXTFETCH_API_KEY not set";
const ZEN = "https://peps.python.org/pep-0020/";
const client = new ContextFetch(undefined, { baseUrl: process.env.CONTEXTFETCH_API_BASE });

test("live: balance", { skip }, async () => {
  assert.equal(typeof (await client.balance()).credits, "number");
});

test("live: search", { skip }, async () => {
  const out = await client.search("python asyncio timeout", { numResults: 3, highlights: true });
  assert.ok(out.results.length > 0);
  assert.match(out.results[0].url, /^http/);
});

test("live: read", { skip }, async () => {
  assert.match((await client.read(ZEN)).markdown, /Beautiful is better than ugly/);
});

test("live: contents", { skip }, async () => {
  const out = await client.contents([ZEN]);
  assert.match(out.results[0].text, /Beautiful is better than ugly/);
});
