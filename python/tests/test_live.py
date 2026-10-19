"""Live smoke test against the real API. Runs only when CONTEXTFETCH_API_KEY is set; uses about 3 credits."""

import os
import unittest

from contextfetch import ContextFetch

ZEN = "https://peps.python.org/pep-0020/"


@unittest.skipUnless(os.environ.get("CONTEXTFETCH_API_KEY"), "CONTEXTFETCH_API_KEY not set")
class LiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = ContextFetch(base_url=os.environ.get("CONTEXTFETCH_API_BASE", "https://api.contextfetch.dev"))

    def test_balance(self) -> None:
        self.assertIsInstance(self.client.balance()["credits"], int)

    def test_search(self) -> None:
        out = self.client.search("python asyncio timeout", num_results=3, highlights=True)
        self.assertGreater(len(out["results"]), 0)
        self.assertTrue(out["results"][0]["url"].startswith("http"))

    def test_read(self) -> None:
        page = self.client.read(ZEN)
        self.assertIn("Beautiful is better than ugly", page.markdown)

    def test_contents(self) -> None:
        out = self.client.contents([ZEN])
        self.assertIn("Beautiful is better than ugly", out["results"][0]["text"])


if __name__ == "__main__":
    unittest.main()
