"""Unit tests against a local fake of the API (stdlib http.server). No network."""

import json
import os
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from contextfetch import (
    APIConnectionError,
    AuthenticationError,
    ContextFetch,
    ContextFetchError,
    Page,
    PaymentRequiredError,
)

PAY_URL = "https://api.contextfetch.dev/buy/instant"
PAYMENT_BODY = {
    "error": "insufficient_credits",
    "message": "This key is out of credits.",
    "checkout_url": "https://contextfetch.dev/#buy",
    "packs": [{"id": "instant", "credits": 1000, "checkout_url": PAY_URL}],
    "action": {"type": "payment_link", "url": PAY_URL, "prompt_to_user": f"ContextFetch credits ran out: {PAY_URL}"},
}


class Handler(BaseHTTPRequestHandler):
    def handle_any(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self.server.requests.append(  # type: ignore[attr-defined]
            {"method": self.command, "path": self.path, "headers": self.headers, "body": json.loads(raw) if raw else None}
        )
        status, headers, payload = self.server.reply  # type: ignore[attr-defined]
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = handle_any

    def log_message(self, *args: object) -> None:
        pass


class ClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.server.requests = []
        self.server.reply = (200, {"Content-Type": "application/json"}, {"results": []})
        self.client = ContextFetch("cf_live_test", base_url=self.base + "/")

    @property
    def last(self) -> dict:
        return self.server.requests[-1]

    def test_search_sends_key_and_camel_case_body(self) -> None:
        self.server.reply = (200, {}, {"requestId": "r1", "results": [{"url": "https://a.example", "text": "# A"}]})
        out = self.client.search("vector databases", num_results=3, exclude_domains=["pinterest.com"], text=True, pruned_context=True)
        self.assertEqual(out["results"][0]["text"], "# A")
        self.assertEqual((self.last["method"], self.last["path"]), ("POST", "/v1/search"))
        self.assertEqual(self.last["headers"]["Authorization"], "Bearer cf_live_test")
        self.assertTrue(self.last["headers"]["User-Agent"].startswith("contextfetch-python/"))
        self.assertEqual(
            self.last["body"],
            {"query": "vector databases", "numResults": 3, "excludeDomains": ["pinterest.com"], "contents": {"text": True, "pruned_context": True}},
        )

    def test_search_without_contents_omits_it(self) -> None:
        self.client.search("q")
        self.assertEqual(self.last["body"], {"query": "q"})

    def test_endpoint_bodies(self) -> None:
        cases = [
            (lambda c: c.find_similar("https://a.example", num_results=2, highlights={"query": "x"}), "/v1/findSimilar",
             {"url": "https://a.example", "numResults": 2, "contents": {"highlights": {"query": "x"}}}),
            (lambda c: c.contents(["https://a.example"]), "/v1/contents", {"urls": ["https://a.example"], "text": True}),
            (lambda c: c.contents(("https://a.example",), text=False, highlights=True), "/v1/contents",
             {"urls": ["https://a.example"], "text": False, "highlights": True}),
            (lambda c: c.answer("why?", num_results=4, text=True), "/v1/answer", {"query": "why?", "numResults": 4, "text": True}),
            (lambda c: c.research("topic", sub_queries=["a", "b"], num_results_per_query=2), "/v1/research",
             {"query": "topic", "subQueries": ["a", "b"], "numResultsPerQuery": 2}),
            (lambda c: c.crawl("https://a.example", limit=5, max_depth=2, query="t", include_paths=["/docs"]), "/v1/crawl",
             {"url": "https://a.example", "limit": 5, "maxDepth": 2, "query": "t", "includePaths": ["/docs"]}),
            (lambda c: c.map("https://a.example", limit=50, exclude_paths=["/blog"]), "/v1/map",
             {"url": "https://a.example", "limit": 50, "excludePaths": ["/blog"]}),
        ]
        for call, path, body in cases:
            with self.subTest(path=path):
                call(self.client)
                self.assertEqual((self.last["method"], self.last["path"], self.last["body"]), ("POST", path, body))

    def test_balance_is_a_get_with_the_key(self) -> None:
        self.server.reply = (200, {}, {"credits": 2499, "auto_reload": {"enabled": False}, "burn_rate_per_day": 1})
        self.assertEqual(self.client.balance()["credits"], 2499)
        self.assertEqual((self.last["method"], self.last["path"], self.last["body"]), ("GET", "/v1/balance", None))
        self.assertEqual(self.last["headers"]["Authorization"], "Bearer cf_live_test")

    def test_free_key_is_sent_without_a_key(self) -> None:
        self.server.reply = (201, {}, {"apiKey": "cf_live_" + "0" * 32, "credits": 2500})
        self.assertEqual(self.client.free_key()["credits"], 2500)
        self.assertEqual((self.last["method"], self.last["path"]), ("POST", "/v1/keys/free"))
        self.assertIsNone(self.last["headers"].get("Authorization"))

    def test_keyless_when_no_key_anywhere(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTEXTFETCH_API_KEY", None)
            ContextFetch(base_url=self.base).search("q")
        self.assertIsNone(self.last["headers"].get("Authorization"))

    def test_key_from_environment(self) -> None:
        with mock.patch.dict(os.environ, {"CONTEXTFETCH_API_KEY": "cf_live_env"}):
            ContextFetch(base_url=self.base).search("q")
        self.assertEqual(self.last["headers"]["Authorization"], "Bearer cf_live_env")

    def test_read_returns_markdown_and_token_headers(self) -> None:
        headers = {"Content-Type": "text/markdown; charset=utf-8", "X-Token-Savings": "91.0", "X-Raw-Tokens": "18240", "X-Output-Tokens": "1650"}
        self.server.reply = (200, headers, "## Task Groups\n\nÜnïcode".encode())
        page = self.client.read("https://docs.python.org/3/library/asyncio-task.html#frag", query="task groups")
        self.assertEqual(page, Page("https://docs.python.org/3/library/asyncio-task.html", "## Task Groups\n\nÜnïcode", 18240, 1650, 91.0))
        self.assertEqual(self.last["path"], "/r/https://docs.python.org/3/library/asyncio-task.html?q=task+groups")

    def test_read_keeps_the_target_query_and_encodes_spaces(self) -> None:
        self.server.reply = (200, {}, b"x")
        page = self.client.read("https://a.example/a b?id=1", query="q")
        self.assertEqual(self.last["path"], "/r/https://a.example/a%20b?id=1&q=q")
        self.assertIsNone(page.raw_tokens)

    def test_402_exposes_payment_link(self) -> None:
        self.server.reply = (402, {"X-Payment-URL": PAY_URL}, PAYMENT_BODY)
        with self.assertRaises(PaymentRequiredError) as ctx:
            self.client.search("q")
        e = ctx.exception
        self.assertEqual((e.status, e.code, e.payment_url), (402, "insufficient_credits", PAY_URL))
        self.assertEqual(e.prompt_to_user, PAYMENT_BODY["action"]["prompt_to_user"])
        self.assertEqual(e.packs[0]["id"], "instant")
        self.assertIn(PAY_URL, str(e))

    def test_402_without_header_falls_back_to_action_url(self) -> None:
        self.server.reply = (402, {}, PAYMENT_BODY)
        with self.assertRaises(PaymentRequiredError) as ctx:
            self.client.read("https://a.example")
        self.assertEqual(ctx.exception.payment_url, PAY_URL)

    def test_401_is_authentication_error(self) -> None:
        self.server.reply = (401, {}, {"error": "invalid_api_key"})
        with self.assertRaises(AuthenticationError) as ctx:
            self.client.balance()
        self.assertEqual((ctx.exception.status, ctx.exception.code), (401, "invalid_api_key"))

    def test_other_errors_carry_status_code_and_message(self) -> None:
        self.server.reply = (503, {}, {"error": "recall_unavailable", "message": "Web search backends are down."})
        with self.assertRaises(ContextFetchError) as ctx:
            self.client.search("q")
        e = ctx.exception
        self.assertNotIsInstance(e, PaymentRequiredError)
        self.assertEqual((e.status, e.code), (503, "recall_unavailable"))
        self.assertIn("Web search backends are down.", str(e))

    def test_validation_error_detail_is_in_the_message(self) -> None:
        self.server.reply = (422, {}, {"detail": [{"loc": ["body", "query"], "msg": "too long"}]})
        with self.assertRaises(ContextFetchError) as ctx:
            self.client.search("q")
        self.assertIn("too long", str(ctx.exception))

    def test_non_json_error_body(self) -> None:
        self.server.reply = (502, {"Content-Type": "text/html"}, b"<html>Bad Gateway</html>")
        with self.assertRaises(ContextFetchError) as ctx:
            self.client.search("q")
        self.assertEqual((ctx.exception.status, ctx.exception.code, ctx.exception.body), (502, None, None))
        self.assertIn("Bad Gateway", str(ctx.exception))

    def test_unreadable_success_body(self) -> None:
        self.server.reply = (200, {}, b"not json")
        with self.assertRaises(ContextFetchError):
            self.client.search("q")

    def test_connection_failure(self) -> None:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with self.assertRaises(APIConnectionError) as ctx:
            ContextFetch("k", base_url=f"http://127.0.0.1:{port}", timeout=5).search("q")
        self.assertIsNone(ctx.exception.status)


if __name__ == "__main__":
    unittest.main()
