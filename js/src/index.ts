// ContextFetch: web search and web pages as Markdown for AI agents.
// A thin client for https://api.contextfetch.dev with no dependencies (global fetch, Node >= 18).
// API reference: https://contextfetch.dev/docs/reference

export const VERSION = "0.1.0";
export const DEFAULT_BASE_URL = "https://api.contextfetch.dev";

/** A contents option: true, or an options object as the API reference describes it, e.g. `{ query: "task groups" }`. */
export type ContentsOption = boolean | Record<string, unknown>;

// ---- responses (JSON as the API returns it) ----

export interface Result {
  id?: string;
  url: string;
  title?: string | null;
  score?: number | null;
  publishedDate?: string | null;
  author?: string | null;
  /** The page as Markdown. */
  text?: string;
  highlights?: string[];
  highlightScores?: number[];
  prunedContext?: string;
  /** research: the sub-queries that found this page. */
  subQueries?: string[];
  /** crawl: link hops from the start URL. */
  depth?: number;
}

export interface CostDollars {
  total: number;
  [k: string]: number;
}

export interface SearchResponse {
  requestId?: string;
  results: Result[];
  costDollars?: CostDollars;
  searchTimeMs?: number;
  /** cache, timingsMs, tokens, sources */
  contextfetch?: Record<string, unknown>;
  notice?: string;
}

export interface ContentsResponse extends SearchResponse {
  statuses?: { id: string; status: "success" | "error"; error?: { tag?: string; message?: string } }[];
}

export interface ResearchResponse extends SearchResponse {
  query: string;
  subQueries: { query: string; status: string; results?: number; error?: string }[];
  /** One Markdown document with numbered [n] sources quoted verbatim. */
  evidence: string;
}

export interface CrawlResponse extends SearchResponse {
  baseUrl: string;
}

export interface Citation {
  id?: string;
  url: string;
  title?: string | null;
  publishedDate?: string | null;
  author?: string | null;
  text?: string;
}

export interface AnswerResponse {
  /** Passages quoted verbatim, each followed by [n]; "" when nothing is relevant enough. */
  answer: string;
  type: "extractive";
  note?: string;
  citations: Citation[];
  /** citation is a 1-based index into citations. */
  passages: { text: string; score: number; citation: number }[];
  costDollars?: CostDollars;
  contextfetch?: Record<string, unknown>;
  notice?: string;
}

export interface MapResponse {
  requestId?: string;
  baseUrl: string;
  results: string[];
  costDollars?: CostDollars;
  contextfetch?: Record<string, unknown>;
  notice?: string;
}

export interface Balance {
  credits: number;
  auto_reload?: {
    enabled?: boolean;
    threshold?: number;
    pack?: string;
    monthly_max_usd?: number;
    spent_this_month_usd?: number;
    last_error?: string | null;
  };
  burn_rate_per_day?: number;
}

export interface FreeKey {
  apiKey: string;
  credits: number;
  /** pack id -> checkout link */
  buy?: Record<string, string>;
}

/** A page read through GET /r/{url}. */
export interface Page {
  url: string;
  markdown: string;
  /** X-Raw-Tokens */
  rawTokens: number | null;
  /** X-Output-Tokens */
  outputTokens: number | null;
  /** X-Token-Savings, percent */
  tokenSavings: number | null;
}

export interface Pack {
  id: string;
  name?: string;
  credits?: number;
  price_usd?: number;
  checkout_url?: string;
  [k: string]: unknown;
}

// ---- request options ----

export interface ContentsOptions {
  text?: ContentsOption;
  highlights?: ContentsOption;
  prunedContext?: ContentsOption;
}

export interface SearchOptions extends ContentsOptions {
  numResults?: number;
  includeDomains?: string[];
  excludeDomains?: string[];
  startPublishedDate?: string;
}

export interface PathOptions {
  limit?: number;
  includePaths?: string[];
  excludePaths?: string[];
}

export interface CrawlOptions extends PathOptions {
  maxDepth?: number;
  maxBreadth?: number;
  query?: string;
}

export interface ClientOptions {
  baseUrl?: string;
  /** Per request, default 60000. */
  timeoutMs?: number;
}

// ---- errors ----

/** An API or transport error. status is null when no response arrived; code is the body's "error" field. */
export class ContextFetchError extends Error {
  readonly status: number | null;
  readonly code: string | null;
  readonly body: unknown;

  constructor(message: string, init: { status?: number | null; code?: string | null; body?: unknown; cause?: unknown } = {}) {
    super(message, { cause: init.cause });
    this.name = new.target.name;
    this.status = init.status ?? null;
    this.code = init.code ?? null;
    this.body = init.body ?? null;
  }
}

/** HTTP 401: the API key is not recognised. */
export class AuthenticationError extends ContextFetchError {}

/**
 * HTTP 402: the key's credits or the keyless daily allowance ran out. Show promptToUser to your human and
 * stop retrying. paymentUrl (the X-Payment-URL header) opens Stripe Checkout in one click.
 */
export class PaymentRequiredError extends ContextFetchError {
  readonly paymentUrl: string | null;
  readonly promptToUser: string | null;
  readonly packs: Pack[];

  constructor(
    message: string,
    init: { status?: number; code?: string | null; body?: unknown; paymentUrl?: string | null; promptToUser?: string | null },
  ) {
    super(message, init);
    this.paymentUrl = init.paymentUrl ?? null;
    this.promptToUser = init.promptToUser ?? null;
    const packs = (init.body as { packs?: unknown } | null)?.packs;
    this.packs = Array.isArray(packs) ? (packs as Pack[]) : [];
  }
}

/** No HTTP response: DNS, connection or timeout failure. */
export class APIConnectionError extends ContextFetchError {}

// ---- client ----

type Json = Record<string, unknown>;

/**
 * Client for the ContextFetch API. apiKey defaults to the CONTEXTFETCH_API_KEY environment variable; with no key
 * the client uses the keyless tier (a small daily allowance per IP). freeKey() returns a starter key with no signup.
 */
export class ContextFetch {
  readonly apiKey: string | null;
  readonly baseUrl: string;
  readonly timeoutMs: number;

  constructor(apiKey?: string, options: ClientOptions = {}) {
    const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
    this.apiKey = (apiKey ?? env?.CONTEXTFETCH_API_KEY) || null;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? 60_000;
  }

  /** POST /v1/search. Results carry page text, highlights or prunedContext only when asked for. */
  search(query: string, options: SearchOptions = {}): Promise<SearchResponse> {
    return this.post("/v1/search", { query, ...searchBody(options) });
  }

  /** POST /v1/findSimilar: pages like url, from other domains. Same shape as search(). */
  findSimilar(url: string, options: SearchOptions = {}): Promise<SearchResponse> {
    return this.post("/v1/findSimilar", { url, ...searchBody(options) });
  }

  /** POST /v1/contents: pages as Markdown. URLs that fail come back in statuses and are not billed. */
  contents(urls: string[], options: ContentsOptions = {}): Promise<ContentsResponse> {
    const { text = true, highlights, prunedContext } = options;
    return this.post("/v1/contents", { urls, text, highlights: highlights || undefined, pruned_context: prunedContext || undefined });
  }

  /** POST /v1/answer: an extractive answer, passages quoted verbatim with [n] citations. Nothing is generated. */
  answer(query: string, options: { numResults?: number; text?: boolean } = {}): Promise<AnswerResponse> {
    return this.post("/v1/answer", { query, numResults: options.numResults, text: options.text || undefined });
  }

  /** POST /v1/research: several searches in one call, ranked together into an evidence pack. */
  research(query: string, options: { subQueries?: string[]; numResultsPerQuery?: number } = {}): Promise<ResearchResponse> {
    return this.post("/v1/research", { query, subQueries: options.subQueries, numResultsPerQuery: options.numResultsPerQuery });
  }

  /** POST /v1/crawl: one site from a start URL, every page as Markdown. robots.txt is obeyed. */
  crawl(url: string, options: CrawlOptions = {}): Promise<CrawlResponse> {
    return this.post("/v1/crawl", { url, ...options });
  }

  /** POST /v1/map: a site's URLs from its links and sitemaps, without fetching the pages. */
  map(url: string, options: PathOptions = {}): Promise<MapResponse> {
    return this.post("/v1/map", { url, ...options });
  }

  /** GET /r/{url}: any public URL as Markdown. With query, only the chunks relevant to it. */
  async read(url: string, options: { query?: string } = {}): Promise<Page> {
    const target = url.replace(/#.*$/s, "");
    // fetch's URL parser percent-encodes spaces and non-ASCII; the target's own query string passes through.
    const q = options.query ? `${target.includes("?") ? "&" : "?"}${new URLSearchParams({ q: options.query })}` : "";
    const res = await this.request("GET", `/r/${target}${q}`);
    const num = (name: string) => {
      const v = res.headers.get(name);
      return v === null || Number.isNaN(Number(v)) ? null : Number(v);
    };
    return {
      url: target,
      markdown: await res.text(),
      rawTokens: num("x-raw-tokens"),
      outputTokens: num("x-output-tokens"),
      tokenSavings: num("x-token-savings"),
    };
  }

  /** GET /v1/balance: credits left on this key and its auto-reload settings. Free. */
  async balance(): Promise<Balance> {
    return json(await this.request("GET", "/v1/balance"));
  }

  /** POST /v1/keys/free: a free starter key, one per network. Sent without this client's key. */
  async freeKey(): Promise<FreeKey> {
    return json(await this.request("POST", "/v1/keys/free", undefined, false));
  }

  // ---- transport ----

  private async post<T>(path: string, body: Json): Promise<T> {
    return json(await this.request("POST", path, body));
  }

  private async request(method: "GET" | "POST", path: string, body?: Json, auth = true): Promise<Response> {
    const headers: Record<string, string> = { "User-Agent": `contextfetch-js/${VERSION}` };
    if (body) headers["Content-Type"] = "application/json";
    if (auth && this.apiKey) headers.Authorization = `Bearer ${this.apiKey}`;
    let res: Response;
    try {
      res = await fetch(this.baseUrl + path, {
        method,
        headers,
        body: body && JSON.stringify(body), // JSON.stringify drops undefined fields
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      const e = err as Error & { cause?: { code?: string; message?: string } };
      const reason = e.name === "TimeoutError" ? `no answer within ${this.timeoutMs} ms` : (e.cause?.code ?? e.cause?.message ?? e.message);
      throw new APIConnectionError(`Could not reach the ContextFetch API at ${this.baseUrl}: ${reason}`, { cause: err });
    }
    if (!res.ok) throw await apiError(res);
    return res;
  }
}

function searchBody(o: SearchOptions): Json {
  const contents = Object.fromEntries(
    Object.entries({ text: o.text, highlights: o.highlights, pruned_context: o.prunedContext }).filter(([, v]) => v),
  );
  return {
    numResults: o.numResults,
    includeDomains: o.includeDomains,
    excludeDomains: o.excludeDomains,
    startPublishedDate: o.startPublishedDate,
    contents: Object.keys(contents).length ? contents : undefined,
  };
}

async function json<T>(res: Response): Promise<T> {
  const raw = await res.text();
  try {
    const data = JSON.parse(raw) as unknown;
    if (data && typeof data === "object" && !Array.isArray(data)) return data as T;
  } catch {
    // fall through
  }
  throw new ContextFetchError(`The ContextFetch API returned an unreadable response: ${raw.slice(0, 200)}`, { status: res.status });
}

async function apiError(res: Response): Promise<ContextFetchError> {
  const raw = await res.text().catch(() => "");
  let body: unknown = null;
  try {
    body = JSON.parse(raw);
  } catch {
    // not JSON, e.g. a proxy's HTML error page
  }
  const info: Json = body && typeof body === "object" && !Array.isArray(body) ? (body as Json) : {};
  const code = typeof info.error === "string" ? info.error : null;
  let detail: unknown = info.message || info.detail || code || raw.slice(0, 300);
  if (typeof detail !== "string") detail = JSON.stringify(detail).slice(0, 300);
  let message =
    `ContextFetch API returned HTTP ${res.status}` + (code ? ` (${code})` : "") + (detail && detail !== code ? `: ${detail}` : "");
  const init = { status: res.status, code, body };
  if (res.status === 401) return new AuthenticationError(message, init);
  if (res.status === 402) {
    const action = (info.action && typeof info.action === "object" ? info.action : {}) as { url?: string; prompt_to_user?: string };
    const promptToUser = action.prompt_to_user ?? null;
    if (promptToUser && !message.includes(promptToUser)) message += ` ${promptToUser}`;
    return new PaymentRequiredError(message, { ...init, paymentUrl: res.headers.get("x-payment-url") ?? action.url ?? null, promptToUser });
  }
  return new ContextFetchError(message, init);
}
