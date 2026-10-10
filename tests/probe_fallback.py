#!/usr/bin/env python
"""Measure the extraction's *fallback ladder* before changing it (live).

keyhole parses a document strictly first; if that yields nothing at all it
parses again with chrome suppression disabled, and again with no heuristics
either. The ladder exists so a heuristic can never turn a page with text into an
empty page — but nothing downstream can see that it fired. A result that came
out of rung 2 or 3 is byte-identical to a page that simply had no chrome.

Three questions, answered with numbers:

1. How often does each rung fire, and does rung 3 ever produce something rung 2
   did not?  (A rung that can never rescue anything is a comment pretending to
   be safety.)
2. When ``scope`` ends up empty, *why*? The empty string currently carries at
   least three different meanings: the page has no content root, a root was
   found but the cut kept nothing, or scoping was switched off by the ladder.
3. What does a silent fallback cost — how many characters of chrome come back
   on a page where rung 2 fired, versus the strict rung that was abandoned?

Outcome (2026-10-09): the probe found (a) rung 3 cannot fire — see fuzz() below,
0 rescues in 400 reaches over 6,000 destructive mutations — so it was deleted
from keyhole; (b) the empty scope carried three meanings (`none` for a page with
no root, `empty-root` for a cut that kept nothing, and scoping switched off by
the ladder), so `SCOPE_EMPTY_ROOT` now names the middle one; (c) the relaxed
pass was silent, so it now reports `parse=no-chrome`. The probe is kept as the
record of why — and as the harness for the next rule that has to earn its place.

Run:  python tests/probe_fallback.py [--fuzz N]
"""
import gzip
import os
import sys
import urllib.request
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keyhole  # noqa: E402
from keyhole import _NoChromeReader, _Reader  # noqa: E402

SITES = [
    ("wikipedia", "https://en.wikipedia.org/wiki/Cloudflare"),
    ("mdn", "https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS"),
    ("npm", "https://www.npmjs.com/package/react"),
    ("peps", "https://peps.python.org/pep-0008/"),
    ("docs.py", "https://docs.python.org/3/library/html.parser.html"),
    ("github", "https://github.com/psf/requests"),
    ("blog.rust", "https://blog.rust-lang.org/"),
    ("example", "https://example.com"),
    ("hn", "https://news.ycombinator.com/news"),
]

# Fixtures for the states the live web may not show. Each is a real shape: a
# malformed document whose text sits inside a chrome class, a root that holds
# nothing, and a JS shell with no text outside dropped tags.
FIXTURES = {
    # A sidebar div opened once and never closed: every word of the page is
    # inside a suppressed subtree, so the strict rung returns nothing.
    "all-inside-chrome": (
        '<body><div class="sidebar"><p>ONLY_TEXT_ON_PAGE</p></body>'
    ),
    # A root that holds nothing: the whole document is kept and the cut is
    # abandoned — which today looks exactly like a page that has no root.
    "empty-root": (
        '<body><div id="chrome"><p>CHROME_TEXT</p></div>'
        '<main></main><p>OUTSIDE_ROOT</p></body>'
    ),
    # A JS shell: no text anywhere outside dropped tags.
    "no-text-at-all": (
        '<html><head><style>.a{}</style></head><body><script>var x=1;</script></body></html>'
    ),
}


class _Traced(_Reader):
    """A _Reader that remembers whether a content root was ever adopted, so the
    probe can tell 'no root in this page' from 'a root was found and dropped'."""

    saw_root = False

    def _adopt_root(self, tag, a):
        super()._adopt_root(tag, a)
        if self._root_at is not None:
            self.saw_root = True

    def why_no_scope(self, rung):
        if self.scope:
            return ""
        if not self._want_scope:
            return "scope-off"
        if not self.saw_root:
            return "no-root"
        return "cut-abandoned"


def rungs(html):
    """Run all three rungs the way _parse used to, returning (rung, readers).

    Rung 3 no longer exists in keyhole; it is still exercised here because
    proving it could never fire is what removed it.
    """
    p1 = keyhole._reader(html, _Traced)
    r1 = keyhole._has_content(p1)
    p2 = keyhole._reader(html, type("T", (_NoChromeReader, _Traced), {}))
    r2 = keyhole._has_content(p2)
    p3 = keyhole._reader(html, type("T", (_NoChromeReader, _Traced), {}), scope=False)
    r3 = keyhole._has_content(p3)
    return (1 if r1 else 2 if r2 else 3), (p1, p2, p3)


def download(url, timeout=25.0):
    req = urllib.request.Request(url, headers=dict(keyhole.BROWSER_HEADERS))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        enc = r.headers.get("Content-Encoding", "")
    if "gzip" in enc.lower():
        raw = gzip.decompress(raw)
    elif "deflate" in enc.lower():
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw.decode("utf-8", "replace")


def report(name, html):
    rung, (p1, p2, p3) = rungs(html)
    used = {1: p1, 2: p2, 3: p3}[rung]
    t_used = len(keyhole._text_of(used))
    line = f"{name:<20} rung={rung}  text={t_used:<7} scope={used.scope or 'none'}"
    if rung == 1 and not used.scope:
        line += f"  ({used.why_no_scope(rung)})"
    if rung > 1:
        # What the relaxed rung bought, and what it cost: rung 1 returned nothing.
        line += f"  [strict was empty; relaxed kept {t_used} chars]"
    if rung == 3:
        t3 = len(keyhole._text_of(p3))
        line += f"  rung3 vs rung2: rung2={bool(p2.md or p2.txt or p2.links)} rung3={bool(p3.md or p3.txt or p3.links)}"
    return rung, line


def fuzz(pages, rounds=20000, seed=0):
    """Does rung 3 ever produce content where rung 2 was empty?

    The ladder's third rung is "no heuristics at all", and it is only reached
    when rung 2 returned nothing. But rung 2 differs from rung 3 *only* in
    scoping, and the scope is abandoned whenever the cut kept nothing — so rung
    3 should be unreachable in the sense that matters: it can never rescue a
    page. Mutate real documents destructively and look for a counterexample.
    """
    import random
    rnd = random.Random(seed)
    tags = ["<div", "<p", "<section", "<main", "<article", "<span", "<ul", "<li", "<h2"]
    attrs = [' class="sidebar"', ' class="cookie-banner"', ' id="main-menu"', ' role="main"',
             ' class="site-nav"', ' aria-hidden="true"', ""]
    violations = []
    reached = 0
    for i in range(rounds):
        src = rnd.choice(pages)
        mode = rnd.randrange(4)
        if mode == 0:                                  # truncate at a random point
            html = src[: rnd.randrange(1, len(src))]
        elif mode == 1:                                # drop a chunk
            a = rnd.randrange(len(src))
            html = src[:a] + src[a + rnd.randrange(1, 4000):]
        elif mode == 2:                                # unbalance: open a container
            a = rnd.randrange(len(src))
            html = src[:a] + rnd.choice(tags) + rnd.choice(attrs) + ">" + src[a:]
        else:                                          # delete closing tags of a kind
            tag = rnd.choice(["div", "p", "section", "main", "article"])
            html = src.replace(f"</{tag}>", "", rnd.randrange(1, 4))
        p2 = keyhole._reader(html, _NoChromeReader)
        if keyhole._has_content(p2):
            continue                                   # rung 3 not reached
        reached += 1
        p3 = keyhole._reader(html, _NoChromeReader, scope=False)
        if keyhole._has_content(p3):
            violations.append((mode, len(html), len(p3.txt)))
    print(f"\n== fuzz: {rounds} mutations of {len(pages)} real pages ==")
    print(f"cases where rung 3 was reached (rung 2 empty): {reached}")
    print(f"rung 3 rescued a page rung 2 could not: {len(violations)}")
    for v in violations[:5]:
        print(f"  COUNTEREXAMPLE mode={v[0]} html_len={v[1]} text_len={v[2]}")
    return violations


def main():
    fuzz_rounds = 0
    if "--fuzz" in sys.argv:
        i = sys.argv.index("--fuzz")
        fuzz_rounds = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 20000
    rungs_seen = {1: 0, 2: 0, 3: 0}
    why = {"no-root": 0, "cut-abandoned": 0, "scope-off": 0}
    pages = []
    print("== live sites ==")
    for name, url in SITES:
        try:
            html = download(url)
        except Exception as e:
            print(f"{name:<20} FETCH FAILED: {type(e).__name__}: {e}")
            continue
        pages.append(html)
        rung, line = report(name, html)
        rungs_seen[rung] += 1
        print(line)
        if rung == 1:
            _, (p1, _, _) = rungs(html)
            w = p1.why_no_scope(1)
            if w:
                why[w] += 1
    print("\n== fixtures ==")
    for name, html in FIXTURES.items():
        rung, line = report(name, html)
        rungs_seen[rung] += 1
        print(line)
        if rung == 1:
            _, (p1, _, _) = rungs(html)
            w = p1.why_no_scope(1)
            if w:
                why[w] += 1
    print(f"\nrungs: strict={rungs_seen[1]}  no-chrome={rungs_seen[2]}  none={rungs_seen[3]}")
    print(f"scope empty because: no-root={why['no-root']}  cut-abandoned={why['cut-abandoned']}  scope-off={why['scope-off']}")
    if fuzz_rounds and pages:
        fuzz(pages, rounds=fuzz_rounds)


if __name__ == "__main__":
    main()
