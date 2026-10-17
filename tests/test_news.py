import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from app.news import (
    FEED_TIMEOUT_SECONDS,
    MAX_FEED_BYTES,
    FeedConfigError,
    FeedSource,
    fetch_news,
    load_sources,
    parse_feed,
)

FIXTURES = Path(__file__).parent / "fixtures"
RSS_SOURCE = FeedSource("RSS local", "https://example.test/rss", "Tecnología")
ATOM_SOURCE = FeedSource("Atom local", "https://example.test/atom", "Economía")


class NewsFeedTests(unittest.TestCase):
    def test_feed_download_is_limited_to_maximum_response_size(self) -> None:
        class OversizedResponse:
            read_limit = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size):
                self.read_limit = size
                return b"x" * size

        response = OversizedResponse()
        with patch("app.news.urlopen", return_value=response):
            items, warnings = fetch_news([RSS_SOURCE])

        self.assertEqual(items, [])
        self.assertEqual(response.read_limit, MAX_FEED_BYTES + 1)
        self.assertEqual(len(warnings), 1)
        self.assertIn("supera el límite", warnings[0])

    def test_reads_rss_and_atom_with_namespaces_and_dates(self) -> None:
        rss_items = parse_feed((FIXTURES / "news_rss.xml").read_bytes(), RSS_SOURCE)
        atom_items = parse_feed((FIXTURES / "news_atom.xml").read_bytes(), ATOM_SOURCE)

        self.assertEqual(len(rss_items), 2)
        self.assertEqual(rss_items[0].title, "Noticia RSS reciente")
        self.assertIsNotNone(rss_items[0].published_at)
        self.assertIsNone(rss_items[1].published)
        self.assertEqual(len(atom_items), 2)
        self.assertEqual(atom_items[0].link, "https://example.test/shared")
        self.assertEqual(atom_items[1].published, "2026-10-15T07:00:00Z")

    def test_deduplicates_by_link_and_sorts_undated_items_last(self) -> None:
        def local_open(request, timeout):
            self.assertEqual(timeout, FEED_TIMEOUT_SECONDS)
            if request.full_url == RSS_SOURCE.url:
                return open(FIXTURES / "news_rss.xml", "rb")
            return open(FIXTURES / "news_atom.xml", "rb")

        with patch("app.news.urlopen", side_effect=local_open):
            items, warnings = fetch_news([RSS_SOURCE, ATOM_SOURCE])

        self.assertEqual(warnings, [])
        self.assertEqual(len(items), 3)
        self.assertEqual(
            [item.link for item in items],
            [
                "https://example.test/atom-new",
                "https://example.test/shared",
                "https://example.test/rss-undated",
            ],
        )
        self.assertEqual(items[1].source, RSS_SOURCE.name)
        self.assertIsNone(items[-1].published_at)

    def test_feed_failure_warns_and_continues_with_other_sources(self) -> None:
        def local_open(request, timeout):
            self.assertEqual(timeout, FEED_TIMEOUT_SECONDS)
            if request.full_url == RSS_SOURCE.url:
                raise URLError("sin conexión simulada")
            return open(FIXTURES / "news_atom.xml", "rb")

        with patch("app.news.urlopen", side_effect=local_open):
            items, warnings = fetch_news([RSS_SOURCE, ATOM_SOURCE])

        self.assertEqual(len(items), 2)
        self.assertEqual(len(warnings), 1)
        self.assertIn(RSS_SOURCE.name, warnings[0])

    def test_malformed_xml_is_reported_as_a_feed_warning(self) -> None:
        with patch(
            "app.news.urlopen",
            return_value=open(FIXTURES / "news_invalid.xml", "rb"),
        ):
            items, warnings = fetch_news([RSS_SOURCE])

        self.assertEqual(items, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn(RSS_SOURCE.name, warnings[0])

    def test_configuration_requires_http_or_https_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "feeds.json"
            config_path.write_text(
                '[{"name":"Local","url":"file:///tmp/feed.xml","topic":"Test"}]',
                encoding="utf-8",
            )

            with self.assertRaises(FeedConfigError):
                load_sources(config_path)


if __name__ == "__main__":
    unittest.main()
