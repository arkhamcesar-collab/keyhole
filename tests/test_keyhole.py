#!/usr/bin/env python
"""Offline tests for keyhole. No network required.

Run:  python tests/test_keyhole.py -v
The regression cases here are real ones this parser shipped with, not invented
hypotheticals — see the docstrings.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keyhole  # noqa: E402


class TestParserSurvival(unittest.TestCase):
    """The parser must degrade gracefully, never silently return nothing."""

    def test_structural_root_is_never_chrome(self):
        """REGRESSION: <html class="...main-menu..."> used to suppress the whole page.

        Wikipedia's <html> carries a class containing "main-menu". An earlier
        version treated that as page chrome, so a 320KB article parsed to zero
        characters while reporting HTTP 200.
        """
        html = ('<html class="client-nojs vector-feature-main-menu-pinned-disabled">'
                '<body><main><h1>Real heading</h1><p>Real body text here.</p></main></body></html>')
        self.assertIn("Real heading", keyhole.html_to_markdown(html))
        self.assertIn("Real body text", keyhole.html_to_text(html))

    def test_unbalanced_tags_do_not_swallow_rest_of_page(self):
        """REGRESSION: a chrome div opened but never closed hid everything after it.

        Depth counters desynchronised; an explicit stack unwinds instead.
        """
        # Distinct tokens: asserting "banner" not in md is a bad test, because the
        # marker heading legitimately contains the word.
        html = ('<body><div class="cookie-banner"><p>COOKIE_NOISE</p></div>'
                '<h1>REAL_HEADING</h1></body>')
        md = keyhole.html_to_markdown(html)
        self.assertNotIn("COOKIE_NOISE", md)
        self.assertIn("REAL_HEADING", md)

    def test_never_closed_chrome_div_is_unwound_by_parent(self):
        html = '<body><div class="sidebar"><p>side</p><div><p>deep</p></div>' \
               '<h2>Content survives</h2></body>'
        self.assertIn("Content survives", keyhole.html_to_markdown(html))

    def test_void_tags_do_not_unbalance_the_stack(self):
        """<br>/<img> arrive with no end tag; pushing them would strand the stack."""
        html = '<body><p>one<br>two<img alt="x" src="y.png"><hr>three</p><h1>Four</h1></body>'
        md = keyhole.html_to_markdown(html)
        self.assertIn("three", md)
        self.assertIn("Four", md)

    def test_self_closing_tags_are_balanced(self):
        html = '<body><div class="a"/><h1>After self close</h1></body>'
        self.assertIn("After self close", keyhole.html_to_markdown(html))


class TestExtraction(unittest.TestCase):

    def test_markdown_structure(self):
        html = ('<html><body><h1>Title</h1>'
                '<p>Intro with <strong>bold</strong> and <a href="/x">a link</a>.</p>'
                '<ul><li>first</li><li>second</li></ul>'
                '<pre>code block</pre></body></html>')
        md = keyhole.html_to_markdown(html)
        self.assertIn("# Title", md)
        self.assertIn("**bold**", md)
        self.assertIn("- first", md)
        self.assertIn("code block", md)

    def test_links_are_absolutised_and_deduped(self):
        html = '<body><a href="/a">A</a><a href="/a">A again</a><a href="#frag">skip</a>' \
               '<a href="javascript:void(0)">js</a></body>'
        links = keyhole.extract_links(html, "https://example.com/page")
        urls = [l["url"] for l in links]
        self.assertEqual(urls, ["https://example.com/a"])

    def test_script_and_style_never_leak_into_text(self):
        html = '<body><script>var secret = "LEAK";</script><style>.x{color:red}</style>' \
               '<p>Visible</p></body>'
        self.assertNotIn("LEAK", keyhole.html_to_text(html))
        self.assertNotIn("color:red", keyhole.html_to_text(html))
        self.assertIn("Visible", keyhole.html_to_text(html))

    def test_metadata_prefers_og_title(self):
        html = '<html><head><meta property="og:title" content="OG Title">' \
               '<meta name="description" content="A description"></head><body>x</body></html>'
        meta = keyhole.extract_metadata(html)
        self.assertEqual(meta["title"], "OG Title")
        self.assertEqual(meta["description"], "A description")

    def test_chrome_patterns_are_narrow(self):
        # A product description must survive a class name that merely looks chrome-ish.
        html = '<body><div class="product-newsletter-card"><p>Product details</p></div></body>'
        self.assertIn("Product details", keyhole.html_to_markdown(html))


class TestWallClassification(unittest.TestCase):

    def test_cloudflare_1010_is_named_not_returned(self):
        wall = keyhole.classify_wall(403, "error code: 1010", {})
        self.assertIsNotNone(wall)
        self.assertEqual(wall[0], "cloudflare_1010")

    def test_js_challenge_is_named(self):
        wall = keyhole.classify_wall(503, "<title>Just a moment...</title>", {})
        self.assertEqual(wall[0], "cloudflare_challenge")

    def test_real_page_is_not_a_wall(self):
        self.assertIsNone(keyhole.classify_wall(200, "<html><body>hello</body></html>", {}))

    def test_tiny_403_is_treated_as_a_block(self):
        wall = keyhole.classify_wall(403, "Forbidden", {"Server": "nginx"})
        self.assertIsNotNone(wall)
        self.assertEqual(wall[0], "http_403")

    def test_browser_headers_carry_a_real_user_agent(self):
        # The whole 1010 fix in one assertion.
        self.assertIn("Mozilla/5.0", keyhole.BROWSER_HEADERS["User-Agent"])


@unittest.skipUnless(os.environ.get("KEYHOLE_NET_TESTS"), "set KEYHOLE_NET_TESTS=1 for live checks")
class TestLive(unittest.TestCase):

    def test_live_fetch_extracts_content(self):
        r = keyhole.fetch("https://example.com")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.ok)
        self.assertIn("Example Domain", r.title)


if __name__ == "__main__":
    unittest.main(verbosity=2)
