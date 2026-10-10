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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/ — for probe_rules

import keyhole  # noqa: E402
import keyhole_mcp  # noqa: E402
import probe_rules  # noqa: E402


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


class TestContentScope(unittest.TestCase):
    """Scoping: drop everything before the page's own content root.

    The failure to guard against is one-directional — a cut that eats the article
    is much worse than a cut that never happens. So every case here has a
    fallback assertion: something real must survive, or the whole page must be
    kept and the scope reported as empty.
    """

    def test_content_before_main_is_not_kept(self):
        """REGRESSION: the corpus file for a Wikipedia article led with
        "Jump to content" and a 60-language switcher before the article."""
        html = ('<body><div id="langlist"><a href="/de">LANG_AFRIKAANS</a></div>'
                '<p>Jump to content</p>'
                '<main><h1>ARTICLE</h1><p>Real body text.</p></main></body>')
        md = keyhole.html_to_markdown(html)
        self.assertNotIn("Jump to content", md)
        self.assertNotIn("LANG_AFRIKAANS", md)
        self.assertIn("# ARTICLE", md)
        self.assertIn("Real body text", md)

    def test_paragraph_tightening_drops_chrome_inside_the_root(self):
        """REGRESSION: Vector 2022 puts the language switcher and the table of
        contents *inside* <main id="content">, so the structural cut cannot reach
        them — Wikipedia improved by only 74 characters because of it. What can
        reach them: the article is the only container in there holding the
        paragraphs, so the cut is narrowed to it, and says so."""
        html = ('<body><p>Jump to content</p><main id="content">'
                '<div id="langs"><a href="/de">LANG_DEUTSCH</a></div>'
                '<div id="toc"><a href="#x">Contents</a></div>'
                '<div id="body"><p>The article opens here.</p>'
                '<p>And continues.</p></div>'
                '<div id="catlinks"><a href="/c">Category</a></div>'
                '</main></body>')
        p = keyhole.analyze(html)
        self.assertEqual(p.scope, "main>div#body")
        md = keyhole._markdown_of(p)
        self.assertIn("The article opens here.", md)
        self.assertIn("And continues.", md)
        self.assertNotIn("LANG_DEUTSCH", md)
        self.assertNotIn("Contents", md)
        # Narrowing never widens: chrome before the root stays dropped.
        self.assertNotIn("Jump to content", md)
        self.assertNotIn("Category", md)

    def test_a_root_without_paragraphs_is_not_tightened(self):
        """The rule keys on <p> text. A root with no paragraphs has nothing to
        tighten against, so the structural scope is reported unchanged."""
        html = '<body><main><div id="wrap"><h1>REAL</h1></div></main></body>'
        p = keyhole.analyze(html)
        self.assertEqual(p.scope, "main")
        self.assertIn("REAL", keyhole._markdown_of(p))

    def test_tightening_never_drops_a_paragraph_it_cannot_cover(self):
        """Two sibling containers split the root's paragraph text; neither covers
        the other, so neither is a candidate and nothing is narrowed. The rule
        keeps the article, it does not pick a piece of it."""
        html = ('<body><main>'
                '<div id="lead"><p>' + "A" * 300 + '</p></div>'
                '<div id="rest"><p>' + "B" * 300 + '</p></div>'
                '</main></body>')
        p = keyhole.analyze(html)
        self.assertEqual(p.scope, "main")
        md = keyhole._markdown_of(p)
        self.assertIn("A" * 300, md)
        self.assertIn("B" * 300, md)

    def test_scope_is_reported_not_guessed(self):
        html = '<body><p>a</p><main><p>REAL</p></main></body>'
        self.assertEqual(keyhole.analyze(html).scope, "main")

    def test_no_root_keeps_the_whole_page_and_says_so(self):
        html = '<body><div><h1>Whole page</h1><p>Kept anyway.</p></div></body>'
        p = keyhole.analyze(html)
        self.assertEqual(p.scope, "")
        self.assertIn("Whole page", keyhole._markdown_of(p))

    def test_empty_main_falls_back_to_the_whole_page(self):
        """A cut that would empty the page is abandoned — and says *that*.

        It used to say nothing: the abandoned cut and "this page has no root at
        all" were both the empty string, so an extraction that was attempted and
        failed read exactly like one that was never attempted.
        """
        html = '<body><p>OUTSIDE_TEXT</p><main></main></body>'
        p = keyhole.analyze(html)
        self.assertEqual(p.scope, keyhole.SCOPE_EMPTY_ROOT)
        self.assertNotEqual(p.scope, "")          # never again the same value as "no root"
        # ...and the row says it, where a reader would see it.
        row = keyhole.format_batch_row(1, 1, keyhole.Result(url="https://x.dev", status=200, text="t", scope=p.scope))
        self.assertIn("scope=empty-root", row)
        row_none = keyhole.format_batch_row(1, 1, keyhole.Result(url="https://x.dev", status=200, text="t"))
        self.assertIn("scope=none", row_none)
        self.assertIn("OUTSIDE_TEXT", keyhole._markdown_of(p))

    def test_role_main_is_a_root(self):
        html = '<body><p>NAV_TEXT</p><div role="main"><h1>REAL</h1></div></body>'
        p = keyhole.analyze(html)
        self.assertEqual(p.scope, "div[role=main]")
        self.assertNotIn("NAV_TEXT", keyhole._markdown_of(p))
        self.assertIn("REAL", keyhole._markdown_of(p))

    def test_article_is_a_weaker_root_than_main(self):
        """A teaser <article> above the real <main> must not win the cut."""
        html = ('<body><article><p>TEASER</p></article><p>MIDDLE</p>'
                '<main><h1>REAL</h1></main></body>')
        p = keyhole.analyze(html)
        self.assertEqual(p.scope, "main")
        md = keyhole._markdown_of(p)
        self.assertNotIn("TEASER", md)
        self.assertNotIn("MIDDLE", md)
        self.assertIn("REAL", md)

    def test_links_are_scoped_too(self):
        """--links on an article page should return the article's links, not the
        site's nav — but only because the nav is really outside the root."""
        html = ('<body><div><a href="/nav">NAV</a></div>'
                '<main><a href="/real">REAL</a></main></body>')
        links = keyhole.extract_links(html, "https://x.dev")
        self.assertEqual([l["url"] for l in links], ["https://x.dev/real"])

    def test_root_like_text_inside_a_script_is_not_a_root(self):
        html = ('<body><script>var tpl = "<main><p>NOT_REAL</p></main>"</script>'
                '<p>KEPT</p></body>')
        p = keyhole.analyze(html)
        self.assertEqual(p.scope, "")
        self.assertIn("KEPT", keyhole._markdown_of(p))


class TestNamedRelaxations(unittest.TestCase):
    """Every heuristic in the extraction is best-effort, so every one of them has
    to say when it gave up: a relaxed pass that stays quiet is indistinguishable
    from a page that never needed relaxing."""

    def test_relaxed_pass_names_itself(self):
        """A malformed document whose whole body sits inside a chrome class comes
        back from the second pass — which used to be invisible."""
        html = '<body><div class="sidebar"><p>ONLY_TEXT_ON_PAGE</p></body>'
        p = keyhole.analyze(html)
        self.assertEqual(p.rung, "no-chrome")
        self.assertIn("ONLY_TEXT_ON_PAGE", keyhole._text_of(p))
        row = keyhole.format_batch_row(1, 1, keyhole.Result(
            url="https://x.dev", status=200, text=keyhole._text_of(p), parse=p.rung))
        self.assertIn("[parse=no-chrome]", row)

    def test_a_clean_page_says_nothing(self):
        """The note is a deviation report: empty means the strict pass, and only
        that. (A marker on every row would be noise; a marker on none of them
        would be the bug this class exists for.)"""
        html = '<body><main><h1>Real</h1><p>Body text here.</p></main></body>'
        p = keyhole.analyze(html)
        self.assertEqual(p.rung, "strict")
        self.assertEqual(keyhole.parse_notes(keyhole.Result(url="u", scope=p.scope)), "")

    def test_whitespace_only_output_is_not_content(self):
        """REGRESSION: a page whose only markdown is a stray <br> counted as
        content — so the fallback ladder stopped one rung early and handed back
        nothing while reporting success. The real text sat inside a chrome class."""
        html = '<body><br><div class="site-nav"><p>REAL_TEXT</p></div></body>'
        self.assertEqual(keyhole.html_to_text(html), "REAL_TEXT")
        self.assertEqual(keyhole.analyze(html).rung, "no-chrome")

    def test_partial_parse_is_named(self):
        """A parser that raises leaves a truncated page. That is usually worth
        keeping — but it is a partial page, and unnamed it reads as a short one."""
        class _Boom(keyhole._Reader):
            def handle_data(self, data):
                if "BOOM" in data:
                    raise ValueError("synthetic parser failure")
                super().handle_data(data)

        p = keyhole._reader('<body><p>Kept.</p><p>BOOM</p><p>After.</p></body>', _Boom)
        self.assertIn("ValueError", p.parse_error)
        self.assertIn("Kept.", keyhole._text_of(p))
        res = keyhole.Result(url="https://x.dev", status=200, text=keyhole._text_of(p),
                             markdown=keyhole._markdown_of(p), parse_error=p.parse_error)
        self.assertIn("[partial: ValueError", keyhole.format_batch_row(1, 1, res))
        self.assertIn("partial: ValueError", keyhole.corpus_body(res).split("\n")[0])
        json_row = keyhole.batch_payload(res)
        self.assertEqual(json_row["parse_error"], p.parse_error)


class TestGuaranteeAudit(unittest.TestCase):
    """tests/probe_rules.py answers "which of keyhole's guarantees actually fire,
    and how much readable text does each one remove?". These tests keep the
    harness honest — a mirror that drifts from the shipped predicate turns its
    numbers into fiction."""

    def test_probe_mirror_matches_the_shipped_predicate(self):
        """probe_rules.chrome_rule re-implements _is_chrome to name the rule that
        matched. It must agree with the shipped predicate on every branch, or the
        audit measures a different tool than the one that ships."""
        battery = [
            ("div", {"class": "sidebar"}),
            ("nav", {}),
            ("footer", {}),
            ("aside", {}),
            ("div", {"class": "cookie-banner"}),
            ("ul", {"id": "main-menu"}),
            ("span", {"aria-hidden": "true"}),
            ("div", {"role": "navigation"}),
            ("div", {"role": "main"}),            # a content root, never chrome
            ("html", {"class": "main-menu"}),     # never chrome: whole-page class
            ("main", {"class": "sidebar"}),       # never chrome: it is the root
            ("p", {"class": "site-nav"}),         # a class-check tag
            ("table", {"id": "cookie-consent"}),
            ("blockquote", {"class": "sidebar"}),  # not a class-check tag
            ("div", {"class": "article-body"}),    # innocent
            ("div", {}),
        ]
        for tag, a in battery:
            self.assertEqual(
                probe_rules.chrome_rule(tag, a) is not None,
                keyhole._Reader._is_chrome(tag, a),
                f"mirror disagrees with _is_chrome on <{tag} {a}>")

    def test_audit_attributes_removals_to_the_rule_that_matched(self):
        """The audit's core claim: a rule that fires removes readable text, per
        rule. If it counted fires but not their effect, a no-op suppression would
        look identical to a working one."""
        html = ('<body><nav>NAVIGATION WORDS</nav>'
                '<div aria-hidden="true">HIDDEN WORDS</div>'
                '<main><p>THE ARTICLE</p></main></body>')
        p = keyhole._reader(html, probe_rules._Audit)
        self.assertEqual(p.scope, "main")
        self.assertEqual(p.fire["tag:nav"][0], 1)
        self.assertGreater(p.fire["tag:nav"][1], 0)
        self.assertEqual(p.fire["aria-hidden"][0], 1)
        self.assertGreater(p.fire["aria-hidden"][1], 0)

    def test_the_override_guarantee_is_visible_to_the_audit(self):
        """Root-override fired 0 times on 9 real pages, so the audit has to be
        able to see it on the shape it exists for. This is the arm for a
        guarantee the wild rarely pulls — the same role test_partial_parse
        plays for the parser's exception catch."""
        html = ('<body><article><p>TEASER</p></article>'
                '<main><p>REAL ARTICLE BODY</p></main></body>')
        a = keyhole._reader(html, probe_rules._Audit)
        self.assertEqual(a.overrode, 1)
        self.assertEqual(a.adoptions, ["article", "article->main"])
        self.assertEqual(a.scope, "main")


class TestTruncationGate(unittest.TestCase):
    """A suppression that keeps the head of the article and eats its tail used to
    ship a stub labelled `parse=strict` — the silent truncation: the empty success
    wearing the costume of a page that simply had little text. Measured by
    tests/probe_truncation.py over 3,000 mutations of nine real pages, up to 99%
    of the root's readable text went missing that way, 14 times, silently. These
    are the shapes that hold the gate honest.
    """

    TAIL = "TAIL_WORD " * 200
    # A suppression opened inside the root and never closed: the classic shape.
    TAIL_EATEN = ('<body><main><p>HEAD_OF_THE_ARTICLE</p>'
                  '<div aria-hidden="true">' + TAIL + '</body>')

    def test_a_chrome_tag_that_eats_the_tail_is_rescued_and_named(self):
        strict = keyhole._reader(self.TAIL_EATEN)
        # The strict pass kept *something* — that is precisely why the old gate
        # ("did anything survive?") let it through and the page read as a short one.
        self.assertTrue(keyhole._has_content(strict))
        self.assertGreater(keyhole.root_lost_share(strict), keyhole.ATE_ROOT)
        rung = keyhole.analyze(self.TAIL_EATEN).rung
        self.assertTrue(rung.startswith("trunc-root:"), rung)
        self.assertIn("TAIL_WORD", keyhole.html_to_markdown(self.TAIL_EATEN))
        # And it is named where a caller will see it, not only in the reader.
        res = keyhole.Result(url="https://x.dev", parse=rung)
        self.assertIn(f"[parse={rung}]", keyhole.parse_notes(res))

    def test_the_share_it_names_is_the_share_it_measured(self):
        """A number in a name is a claim: `trunc-root:99%` says 99% of the root's
        readable text was thrown away. Fiction there is worse than silence."""
        strict = keyhole._reader(self.TAIL_EATEN)
        printed = keyhole.analyze(self.TAIL_EATEN).rung.split(":")[1].rstrip("%")
        self.assertEqual(int(printed),
                         round(keyhole.root_lost_share(strict) * 100))
        self.assertGreaterEqual(int(printed), keyhole.ATE_ROOT * 100)

    def test_chrome_legitimately_inside_the_root_does_not_trip_the_gate(self):
        """nav, asides and footers *should* go — including when the page's own
        root wraps them. Only losing more than was kept is a truncation, and no
        clean page in the probe's nine comes near the gate (worst: npm, 23%)."""
        body = "ARTICLE " * 100
        html = (f'<body><main><p>{body}</p><aside>RELATED LINKS</aside>'
                f'<p>{body}</p></main></body>')
        r = keyhole.analyze(html)
        self.assertEqual(r.rung, "strict")
        self.assertNotIn("RELATED LINKS", keyhole._text_of(r))
        self.assertLessEqual(keyhole.root_lost_share(r), keyhole.ATE_ROOT)

    def test_a_script_inside_the_root_is_dropped_not_lost(self):
        """The first version of this counter charged every suppressed byte to
        chrome, so an inline `<script>` inside `<main>` counted as article text
        thrown away — MDN then read 40% and GitHub 90%, both measuring their own
        code. Losing the page and dropping a script are different events, which
        is why the tag stack carries *why* it suppressed, not just that it did."""
        html = ('<body><main><p>SHORT ARTICLE</p>'
                '<script>var x = "' + "padding " * 500 + '";</script>'
                '<style>.a{color:red}</style></main></body>')
        p = keyhole._reader(html)
        self.assertEqual(p.sup_in_root, 0)
        self.assertEqual(keyhole.root_lost_share(p), 0.0)
        self.assertEqual(keyhole.analyze(html).rung, "strict")
        self.assertIn("SHORT ARTICLE", keyhole._text_of(p))

    def test_nothing_survived_says_no_chrome_not_trunc_root(self):
        """The two relaxations are two different facts — nothing survived, or a
        minority survived and was discarded. Giving them one symbol would be the
        `scope=""` mistake over again."""
        html = '<body><div class="sidebar"><p>ONLY_TEXT_ON_PAGE</p></div></body>'
        p = keyhole.analyze(html)
        self.assertEqual(p.rung, "no-chrome")
        self.assertIn("ONLY_TEXT_ON_PAGE", keyhole._text_of(p))

    def test_a_tag_dropped_inside_chrome_is_dropped_not_charged_to_chrome(self):
        """The witness for the hole `probe_drop` measured: `_DROP_TAGS` used to be
        asked only when nothing else was already suppressing, so a `<style>`
        nested inside a chrome frame inherited `chrome` as its reason and its CSS
        arrived as `data` — read as words a reader would have seen. On the honest
        corpus that is 8,273 characters, 19.8% of everything the counter counts.
        The reason a frame is dropped is its tag, not the frame it sits in."""
        css = ".x{color:red;}" * 300
        html = ('<body><main><p>SHORT ARTICLE</p>'
                '<div class="sidebar"><style>' + css + '</style>NAV_WORD'
                '</div></main></body>')
        p = keyhole._reader(html)
        self.assertIn("SHORT ARTICLE", keyhole._text_of(p))
        # The nav inside the root is chrome, and chrome is allowed to cost
        # something — this is the count that has to stay a count: eight
        # characters of nav, and not one of the 4,500 of CSS beside it.
        self.assertEqual(p.sup_in_root, len("NAV_WORD"))
        self.assertLess(p.sup_in_root, len(css))
        self.assertEqual(keyhole.analyze(html).rung, "strict")

    def test_css_counted_as_prose_no_longer_trips_the_gate_by_itself(self):
        """Why the hole reached the shipped gate and not only a probe: CSS read as
        prose is enough on its own to push an honest page past `ATE_ROOT`. Here
        the payload is bigger than the whole article kept, so the gate would
        relax a page whose article is intact — the exact false positive the
        uncurated corpus found in Torrebaja, reachable without a navbox."""
        css = ".x{color:red;}" * 300
        body = "ARTICLE " * 40
        html = ('<body><main><p>' + body + '</p>'
                '<div class="sidebar"><style>' + css + '</style>RELATED'
                '</div></main></body>')
        p = keyhole._reader(html)
        # The claim the witness rests on: the payload alone outweighs the kept text.
        self.assertGreater(len(css), len(keyhole._text_of(p)))
        self.assertLessEqual(keyhole.root_lost_share(p), keyhole.ATE_ROOT)
        self.assertFalse(keyhole.ate_the_root(p))
        self.assertEqual(keyhole.analyze(html).rung, "strict")
        self.assertIn("ARTICLE", keyhole._text_of(p))

    def test_the_gate_never_trips_on_the_audited_fixtures(self):
        """Every fixture in probe_rules is a shape keyhole must handle *without*
        relaxing. A gate that fires on one of them is eating pages that were
        already right."""
        for name, html in probe_rules.FIXTURES.items():
            p = keyhole._reader(html)
            self.assertFalse(keyhole.ate_the_root(p),
                             f"the gate trips on fixture {name!r}: "
                             f"{keyhole.root_lost_share(p):.0%} of the root lost")

    def test_a_tiny_root_losing_most_of_itself_is_not_a_truncation(self):
        """`<main><p>REAL</p><div aria-hidden>hidden</div></main>` loses 60% of
        its root — over the share gate — and there is no article to rescue: four
        words kept, six dropped. The share is scale-free and meaningless at that
        size, which is why the gate also requires a loss bigger than the 200
        characters this tool already calls an empty page."""
        html = probe_rules.FIXTURES["aria-hidden-content"]
        p = keyhole._reader(html)
        self.assertGreater(keyhole.root_lost_share(p), keyhole.ATE_ROOT)
        self.assertLessEqual(p.sup_in_root, keyhole.EMPTY_TEXT)
        self.assertFalse(keyhole.ate_the_root(p))
        self.assertEqual(keyhole.analyze(html).rung, "strict")

    def test_the_probe_itemises_the_same_drops_the_gate_counts(self):
        """probe_truncation's instrument attributes each in-root drop to a rule;
        the gate counts them. If the attribution drifts from the shipped reason
        tracking, the probe's record of *why the gate sits at 50%* is fiction."""
        import probe_truncation
        for name, html in list(probe_rules.FIXTURES.items()) + [("tail-eaten", self.TAIL_EATEN)]:
            pr = keyhole._reader(html, probe_truncation._Trunc)
            self.assertEqual(sum(pr.by_label.values()), pr.sup_in_root, name)
            self.assertEqual(keyhole._reader(html).sup_in_root, pr.sup_in_root, name)


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

    def test_big_200_page_is_not_a_wall_despite_challenge_strings(self):
        """REGRESSION: Wikipedia was flagged as a CAPTCHA wall while returning 21k
        chars of real article, because its HTML embeds a reCAPTCHA form."""
        body = "<html><body>" + ("real content " * 2000) + "<div class='g-recaptcha'></div></body></html>"
        self.assertIsNone(keyhole.classify_wall(200, body, {}))

    def test_small_200_challenge_page_is_still_a_wall(self):
        self.assertEqual(keyhole.classify_wall(200, "<title>Just a moment...</title>", {})[0],
                         "cloudflare_challenge")

    def test_tiny_403_is_treated_as_a_block(self):
        wall = keyhole.classify_wall(403, "Forbidden", {"Server": "nginx"})
        self.assertIsNotNone(wall)
        self.assertEqual(wall[0], "http_403")

    def test_browser_headers_carry_a_real_user_agent(self):
        # The whole 1010 fix in one assertion.
        self.assertIn("Mozilla/5.0", keyhole.BROWSER_HEADERS["User-Agent"])


class TestBatch(unittest.TestCase):
    """Batch mode: the input parser and the report row. Offline, pure functions."""

    def test_parse_drops_blanks_and_comments(self):
        urls = keyhole.parse_url_list("\n# a comment\nhttps://a.dev\n\n   \nhttps://b.dev\n")
        self.assertEqual(urls, ["https://a.dev", "https://b.dev"])

    def test_parse_dedupes_keeping_first_occurrence_and_order(self):
        urls = keyhole.parse_url_list("https://c.dev\nhttps://a.dev\nhttps://c.dev\n")
        self.assertEqual(urls, ["https://c.dev", "https://a.dev"])

    def test_parse_does_not_treat_hash_as_inline_comment(self):
        """A URL fragment is not a comment. Truncating it would fetch the wrong
        page and report success, which is worse than an error."""
        urls = keyhole.parse_url_list("https://a.dev/post#section-2\n")
        self.assertEqual(urls, ["https://a.dev/post#section-2"])

    def test_run_batch_returns_input_order_even_if_completion_differs(self):
        import time
        order = []

        def fake(url, timeout=25.0, do_render=False):
            # The first URL is deliberately the slowest: if run_batch collected by
            # completion time instead of input position, it would come back last.
            time.sleep(0.05 if url == "https://slow.dev" else 0.0)
            order.append(url)
            r = keyhole.Result(url=url, status=200, text="body text")
            return r

        real = keyhole.fetch_maybe_render
        keyhole.fetch_maybe_render = fake
        try:
            res = keyhole.run_batch(["https://slow.dev", "https://fast.dev"], jobs=2)
        finally:
            keyhole.fetch_maybe_render = real
        self.assertEqual([r.url for r in res], ["https://slow.dev", "https://fast.dev"])
        self.assertEqual(sorted(order), ["https://fast.dev", "https://slow.dev"])

    def test_row_names_a_wall_instead_of_reporting_generic_failure(self):
        r = keyhole.Result(url="https://x.dev", status=403,
                           wall={"kind": "cloudflare_1010", "why": "nope"})
        row = keyhole.format_batch_row(1, 2, r)
        self.assertIn("WALL cloudflare_1010", row)

    def test_row_shows_error_text(self):
        r = keyhole.Result(url="https://x.dev", error="ConnectTimeout: timed out after 25s")
        row = keyhole.format_batch_row(1, 1, r)
        self.assertIn("ERR", row)
        self.assertIn("https://x.dev", row)
        # The URL leads and the reason is not cut to 22 chars mid-word.
        self.assertIn("ConnectTimeout: timed out after 25s", row)

    def test_row_marks_a_rendered_result(self):
        r = keyhole.Result(url="https://spa.dev", status=200, method="browser",
                           text="rendered body", title="SPA")
        self.assertIn("[rendered]", keyhole.format_batch_row(1, 1, r))

    def test_payload_carries_counts_not_bodies(self):
        r = keyhole.Result(url="https://x.dev", status=200, text="12345", markdown="# big")
        p = keyhole.batch_payload(r)
        self.assertEqual(p["text_chars"], 5)
        self.assertNotIn("text", p)
        self.assertNotIn("markdown", p)
        self.assertTrue(p["ok"])

    def test_render_is_not_attempted_on_a_clean_result(self):
        """--render escalates unusable results; it must not spend a browser on a
        page that already came back fine."""
        calls = []
        real_fetch, real_render = keyhole.fetch, keyhole.render
        keyhole.fetch = lambda url, timeout=25.0: keyhole.Result(
            url=url, status=200, text="plenty of real text " * 20)
        keyhole.render = lambda url, timeout=40: calls.append(url) or keyhole.Result(url=url)
        try:
            keyhole.fetch_maybe_render("https://fine.dev", do_render=True)
        finally:
            keyhole.fetch, keyhole.render = real_fetch, real_render
        self.assertEqual(calls, [])

    def test_render_escalates_a_client_rendered_shell(self):
        """A shell is HTTP 200 with almost no text: res.ok is True, so ok alone
        cannot be the gate or the SPA is never rendered."""
        calls = []
        real_fetch, real_render = keyhole.fetch, keyhole.render
        keyhole.fetch = lambda url, timeout=25.0: keyhole.Result(
            url=url, status=200, bytes_in=9000, text="")
        keyhole.render = lambda url, timeout=40: calls.append(url) or keyhole.Result(
            url=url, status=200, method="browser", text="real rendered content")
        try:
            res = keyhole.fetch_maybe_render("https://spa.dev", do_render=True)
        finally:
            keyhole.fetch, keyhole.render = real_fetch, real_render
        self.assertEqual(calls, ["https://spa.dev"])
        self.assertEqual(res.method, "browser")


class TestCorpus(unittest.TestCase):
    """batch --out DIR: one file per URL. Offline — filenames and bodies are pure."""

    def test_slug_is_filesystem_safe(self):
        s = keyhole.slug_for_url("https://en.wikipedia.org/wiki/Cloudflare (bot)?x=1&y=2#frag")
        self.assertRegex(s, r"^[a-z0-9._-]+$")
        self.assertTrue(s.startswith("en.wikipedia.org-wiki-cloudflare"))

    def test_slug_drops_www_and_page_extension(self):
        self.assertEqual(keyhole.slug_for_url("https://www.example.com/a/b.html"), "example.com-a-b")

    def test_slug_drops_fragment_but_keeps_query(self):
        """A fragment names the same resource; a query can name a different page."""
        self.assertEqual(keyhole.slug_for_url("https://a.dev/p#s2"), "a.dev-p")
        self.assertNotEqual(keyhole.slug_for_url("https://a.dev/p?id=1"),
                            keyhole.slug_for_url("https://a.dev/p?id=2"))

    def test_slug_never_a_reserved_windows_name(self):
        """Only an exact stem ('con', not 'con-prn') is illegal on Windows."""
        self.assertEqual(keyhole.slug_for_url("https://con"), "_con")
        self.assertEqual(keyhole.slug_for_url("https://nul/x"), "nul-x")
        self.assertEqual(keyhole.slug_for_url("https://con/prn"), "con-prn")

    def test_slug_is_length_capped_for_windows_paths(self):
        s = keyhole.slug_for_url("https://a.dev/" + "segment/" * 60)
        self.assertLessEqual(len(s), 80)

    def test_collisions_are_numbered_by_input_order(self):
        taken = set()
        self.assertEqual(keyhole.corpus_filename("https://a.dev/p#one", taken), "a.dev-p.md")
        self.assertEqual(keyhole.corpus_filename("https://a.dev/p#two", taken), "a.dev-p-2.md")
        self.assertEqual(keyhole.corpus_filename("https://a.dev/p#three", taken), "a.dev-p-3.md")

    def test_body_carries_source_and_content(self):
        r = keyhole.Result(url="https://x.dev", status=200, title="Hi", markdown="# Hi\n\nbody")
        body = keyhole.corpus_body(r)
        self.assertIn("<!-- source: https://x.dev | scope: none (whole page) -->", body)
        self.assertIn("body", body)
        # The extraction already led with the title: no doubled H1.
        self.assertEqual(body.count("# Hi"), 1)

    def test_body_names_the_scope_it_used(self):
        """A corpus file must say whether it is the article or the whole page —
        otherwise a scoping that did nothing looks exactly like one that worked."""
        r = keyhole.Result(url="https://x.dev", status=200, markdown="body", scope="main")
        self.assertIn("scope: main", keyhole.corpus_body(r))

    def test_body_adds_title_when_extraction_had_none(self):
        r = keyhole.Result(url="https://x.dev", status=200, title="Hi", markdown="body text")
        self.assertIn("# Hi", keyhole.corpus_body(r))

    def test_body_names_a_wall_instead_of_writing_an_empty_file(self):
        """The whole point: a walled page leaves a visible hole, not a silent one."""
        r = keyhole.Result(url="https://x.dev", status=403,
                           wall={"kind": "cloudflare_1010", "why": "bad UA"})
        body = keyhole.corpus_body(r)
        self.assertIn("FAILED", body)
        self.assertIn("WALL cloudflare_1010", body)

    def test_body_names_an_error(self):
        r = keyhole.Result(url="https://x.dev", error="URLError: timed out")
        self.assertIn("ERROR: URLError: timed out", keyhole.corpus_body(r))

    def test_write_corpus_writes_every_url_including_failures(self):
        import tempfile
        results = [keyhole.Result(url="https://a.dev/x", status=200, markdown="hello"),
                   keyhole.Result(url="https://b.dev/y", status=403,
                                  wall={"kind": "datadome", "why": "nope"})]
        with tempfile.TemporaryDirectory() as d:
            written = keyhole.write_corpus(results, d)
            files = sorted(os.listdir(d))
        self.assertEqual(files, ["a.dev-x.md", "b.dev-y.md"])
        self.assertEqual([n for _, n in written], ["a.dev-x.md", "b.dev-y.md"])


class TestMCPFetchMany(unittest.TestCase):
    """The fetch_many tool. Network is stubbed: this locks the report shape and
    the isError rule, not the fetching."""

    def _call(self, args, results):
        real = keyhole.run_batch
        keyhole.run_batch = lambda urls, **kw: results
        try:
            return keyhole_mcp.tool_fetch_many(args)
        finally:
            keyhole.run_batch = real

    def test_empty_urls_is_an_error(self):
        out = keyhole_mcp.tool_fetch_many({"urls": []})
        self.assertTrue(out["isError"])
        self.assertIn("non-empty", out["content"][0]["text"])

    def test_rejects_non_string_junk(self):
        out = keyhole_mcp.tool_fetch_many({"urls": [1, None, "  "]})
        self.assertTrue(out["isError"])

    def test_accepts_a_newline_separated_string(self):
        seen = {}

        def fake(urls, **kw):
            seen["urls"] = urls
            return [keyhole.Result(url=u, status=200, text="body") for u in urls]

        real = keyhole.run_batch
        keyhole.run_batch = fake
        try:
            keyhole_mcp.tool_fetch_many({"urls": "# notes\nhttps://a.dev\nhttps://b.dev\n"})
        finally:
            keyhole.run_batch = real
        self.assertEqual(seen["urls"], ["https://a.dev", "https://b.dev"])

    def test_partial_success_is_not_an_error(self):
        """One dead URL out of two still answers the question asked, so it must
        not be flagged isError — that would invite a pointless retry."""
        results = [keyhole.Result(url="https://a.dev", status=200, text="body"),
                   keyhole.Result(url="https://b.dev", error="URLError: nope")]
        out = self._call({"urls": ["https://a.dev", "https://b.dev"]}, results)
        self.assertFalse(out["isError"])
        self.assertIn("1/2 ok", out["content"][0]["text"])

    def test_total_failure_is_an_error(self):
        results = [keyhole.Result(url="https://a.dev", error="URLError: nope")]
        out = self._call({"urls": ["https://a.dev"]}, results)
        self.assertTrue(out["isError"])
        self.assertIn("0/1 ok", out["content"][0]["text"])

    def test_hint_only_appears_when_a_wall_is_unrendered(self):
        walled = [keyhole.Result(url="https://a.dev", status=403,
                                 wall={"kind": "cloudflare_1010", "why": "x"})]
        out = self._call({"urls": ["https://a.dev"]}, walled)
        self.assertIn("hint: render=true", out["content"][0]["text"])
        out = self._call({"urls": ["https://a.dev"], "render": True}, walled)
        self.assertNotIn("hint: render=true", out["content"][0]["text"])


@unittest.skipUnless(os.environ.get("KEYHOLE_NET_TESTS"), "set KEYHOLE_NET_TESTS=1 for live checks")
class TestLive(unittest.TestCase):

    def test_live_fetch_extracts_content(self):
        r = keyhole.fetch("https://example.com")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.ok)
        self.assertIn("Example Domain", r.title)


if __name__ == "__main__":
    unittest.main(verbosity=2)
