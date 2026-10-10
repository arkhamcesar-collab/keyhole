#!/usr/bin/env python
"""Audit which extraction guarantees actually fire, and what each one does.

The sixth awakening found a *fallback rung that could not fire* and deleted it.
The question it left open is bigger: how many of keyhole's /other/ guarantees are
the same shape? A rule that can never match, or a rule that matches but removes
nothing, is a comment pretending to be safety — and it reads exactly like a rule
that works.

This probe instruments a _Reader so every guarantee reports two numbers over a
corpus of real pages and destructive mutations:

    fires    — how many times the guarantee matched
    removed  — non-whitespace characters of readable text it took off the page

A guarantee with fires=0 cannot fire. A guarantee with fires>0 but removed=0 fires
into a vacuum. Both are the empty-success shape in a different costume. The probe
prints them as ALERT lines instead of hiding them in a total.

Run:  python tests/probe_rules.py [--fuzz N]
"""
import gzip
import os
import random
import sys
import urllib.request
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keyhole  # noqa: E402
from keyhole import _Reader  # noqa: E402

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

# Fixtures for shapes the live web may not hand us. Each targets one guarantee.
FIXTURES = {
    "all-inside-chrome": '<body><div class="sidebar"><p>ONLY_TEXT_ON_PAGE</p></body>',
    "empty-root": ('<body><div id="chrome"><p>CHROME_TEXT</p></div>'
                   '<main></main><p>OUTSIDE_ROOT</p></body>'),
    "no-text-at-all": ('<html><head><style>.a{}</style></head>'
                       '<body><script>var x=1;</script></body></html>'),
    "aria-hidden-content": '<body><main><p>REAL</p><div aria-hidden="true"><p>hidden</p></div></main></body>',
    "role-nav": '<body><main><p>REAL</p><div role="banner">a banner</div></main></body>',
    "two-roots": '<body><article>teaser</article><main><p>REAL ARTICLE BODY</p></main></body>',
}


def chrome_rule(tag: str, a: dict):
    """Mirror _Reader._is_chrome but name the rule that matched, or None.

    Kept as an explicit mirror (not a rewrite of the shipped rule) so the probe
    measures the shipped predicate: test_keyhole asserts the two agree on the
    fixtures, and probe output flags a drift.
    """
    if tag in _Reader._NEVER_CHROME:
        return None
    if tag in keyhole._CHROME_TAGS:
        return f"tag:{tag}"
    role = a.get("role")
    if role in ("navigation", "banner", "contentinfo", "complementary"):
        return f"role={role}"
    if a.get("aria-hidden") == "true":
        return "aria-hidden"
    if tag not in _Reader._CLASS_CHECK_TAGS:
        return None
    m = keyhole._CHROME_PATTERNS.search(f"{a.get('id', '')} {a.get('class', '')}")
    return f"class:{m.group(0).lower()}" if m else None


class _Audit(_Reader):
    """A _Reader that attributes every suppression to its rule and counts the
    readable characters each one removes, plus the root and tightening events."""

    def __init__(self, scope: bool = True):
        super().__init__(scope)
        self.fire: dict[str, list[int]] = {}   # rule -> [fires, chars_removed]
        self.adoptions: list[str] = []          # every root adopted, in order
        self.overrode = 0                       # times a stronger root replaced a weaker
        self.tighten_fired = 0
        self.tighten_chars = 0
        self.parse_error_hits = 0
        self.by_label: dict[str, int] = {}     # "rule @ tag#id.class" -> chars removed
        self._arec: list = []                   # parallel to _stack: suppression record or None

    def _count_fire(self, rule):
        self.fire.setdefault(rule, [0, 0])[0] += 1

    def _add_chars(self, rule, n):
        self.fire.setdefault(rule, [0, 0])[1] += n

    # _is_chrome is a staticmethod on the base; as an instance method here the
    # call site `self._is_chrome(tag, a)` passes self and we can record.
    def _is_chrome(self, tag, a):
        r = chrome_rule(tag, a)
        return r is not None

    def _adopt_root(self, tag, a):
        before = self._root_at is not None
        strong_before = self._root_tag
        super()._adopt_root(tag, a)
        if self._root_at is not None and self.scope and (
                not before or self._root_tag != strong_before):
            if before:
                self.overrode += 1
                self.adoptions.append(f"{strong_before}->{self._root_tag}")
            else:
                self.adoptions.append(self._root_tag)

    def _tightest(self, *span):
        best = super()._tightest(*span)
        if best is not None:
            self.tighten_fired += 1
        return best

    # -- stack mirror so handle_data can attribute characters to a rule
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = self._attrs(attrs)
        rule = chrome_rule(tag, a)
        was_sup = self._suppressed()
        rec = None
        if tag not in keyhole._VOID_TAGS:
            if not was_sup and rule:
                lbl = _Reader._attr_label(tag, a)
                self._arec.append([rule, 0, f"{rule} @ {lbl}"])
                self._count_fire(rule)
            elif was_sup:
                rec = next((e for e in reversed(self._arec) if e is not None), None)
                self._arec.append(rec)
            else:
                self._arec.append(None)
        super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        # _arec mirrors _stack one frame per non-void tag; find the matching
        # frame the same way the base class does, then trim both together.
        idx = None
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                idx = i
                break
        if idx is not None:
            del self._arec[len(self._arec) - (len(self._stack) - idx):]
        super().handle_endtag(tag)

    def handle_data(self, data):
        if data.strip() and self._suppressed():
            rec = next((e for e in reversed(self._arec) if e is not None), None)
            if rec is not None:
                rec[1] += len(data)
                self._add_chars(rec[0], len(data))
                self.by_label[rec[2]] = self.by_label.get(rec[2], 0) + len(data)
        super().handle_data(data)


def audit(html):
    """Instrument one parse, and also report which rung the *shipped* ladder
    lands on for this page (the ladder itself is invisible to an instrumented
    reader, so it is asked separately)."""
    p = keyhole._reader(html, _Audit)
    if p.parse_error:
        p.parse_error_hits += 1
    real = keyhole.analyze(html)
    p.rung = real.rung
    p.parse_error = real.parse_error
    return p


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


def fuzz(pages, rounds, seed=0):
    """Mutate real pages destructively and total each rule's removals, so a rule
    that only ever fires on a broken page still gets counted. Also counts the
    two guarantees that never fired on clean pages: the root-override and the
    parser-error catch, both asked of the shipped ladder."""
    rnd = random.Random(seed)
    tags = ["<div", "<p", "<section", "<main", "<article", "<span", "<ul", "<li", "<nav", "<aside"]
    attrs = [' class="sidebar"', ' class="cookie-banner"', ' id="main-menu"', ' role="main"',
             ' role="navigation"', ' class="site-nav"', ' aria-hidden="true"', " "]
    total: dict[str, list[int]] = {}
    tight = relaxed = overrides = parse_err = 0
    for _ in range(rounds):
        src = rnd.choice(pages)
        mode = rnd.randrange(4)
        if mode == 0:
            html = src[: rnd.randrange(1, len(src))]
        elif mode == 1:
            a = rnd.randrange(len(src))
            html = src[:a] + src[a + rnd.randrange(1, 4000):]
        elif mode == 2:
            a = rnd.randrange(len(src))
            html = src[:a] + rnd.choice(tags) + rnd.choice(attrs) + ">" + src[a:]
        else:
            tag = rnd.choice(["div", "p", "section", "main", "article"])
            html = src.replace(f"</{tag}>", "", rnd.randrange(1, 4))
        p = keyhole._reader(html, _Audit)
        if p.tighten_fired:
            tight += 1
        overrides += p.overrode
        if p.parse_error:
            parse_err += 1
        if not keyhole._has_content(p):
            relaxed += 1
        for k, v in p.fire.items():
            slot = total.setdefault(k, [0, 0])
            slot[0] += v[0]
            slot[1] += v[1]
    return total, tight, relaxed, overrides, parse_err


def show(label, agg):
    print(f"\n== {label} ==")
    if not agg:
        print("(nothing fired)")
        return
    width = max(len(k) for k in agg)
    for k in sorted(agg):
        fires, chars = agg[k]
        flag = ""
        if fires == 0:
            flag = "  <-- ALERT: cannot fire"
        elif chars == 0:
            flag = "  <-- ALERT: fired but removed nothing readable"
        print(f"  {k:<{width}}  fires={fires:<7} removed={chars}{flag}")


def merge(agg, p):
    for k, v in p.fire.items():
        slot = agg.setdefault(k, [0, 0])
        slot[0] += v[0]
        slot[1] += v[1]


def main():
    fuzz_rounds = 0
    if "--fuzz" in sys.argv:
        i = sys.argv.index("--fuzz")
        fuzz_rounds = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 5000
    live_agg: dict[str, list[int]] = {}
    fix_agg: dict[str, list[int]] = {}
    labels: dict[str, int] = {}
    pages = []
    adopt_seen = {}
    overrides_live = overrides_fix = 0
    tight_live = tight_fix = 0
    relaxed_live = relaxed_fix = 0
    print(f"keyhole {keyhole.__version__} — which guarantees fire?\n")
    print("== live sites ==")
    for name, url in SITES:
        try:
            html = download(url)
        except Exception as e:
            print(f"{name:<12} FETCH FAILED: {type(e).__name__}: {e}")
            continue
        pages.append(html)
        p = audit(html)
        merge(live_agg, p)
        for k, v in p.by_label.items():
            labels[k] = labels.get(k, 0) + v
        for a in p.adoptions:
            adopt_seen[a] = adopt_seen.get(a, 0) + 1
        overrides_live += p.overrode
        tight_live += p.tighten_fired
        relaxed_live += 1 if p.rung == "no-chrome" else 0
        print(f"{name:<12} scope={p.scope or 'none':<40} roots={p.adoptions} "
              f"tighten={p.tighten_fired} parse={p.rung}")
    print("\n== fixtures ==")
    for name, html in FIXTURES.items():
        p = audit(html)
        merge(fix_agg, p)
        overrides_fix += p.overrode
        tight_fix += p.tighten_fired
        relaxed_fix += 1 if p.rung == "no-chrome" else 0
        print(f"{name:<20} scope={p.scope or 'none':<28} roots={p.adoptions} "
              f"tighten={p.tighten_fired} parse={p.rung}")
    show("chrome rules — live sites only", live_agg)
    show("chrome rules — fixtures only", fix_agg)
    noop = {k: v for k, v in labels.items() if v == 0}
    if noop:
        print(f"\n== chrome fires into a vacuum (matched, removed 0 readable chars) ==")
        for k in sorted(noop):
            print(f"  {k}")
    print(f"\nroot adoptions seen on live sites: {adopt_seen}")
    print(f"root-override events: live={overrides_live}  fixtures={overrides_fix}")
    print(f"paragraph-tightening fired: live={tight_live}  fixtures={tight_fix}")
    print(f"relaxed pass (parse=no-chrome) used: live={relaxed_live}  fixtures={relaxed_fix}")
    if fuzz_rounds and pages:
        total, tight, relaxed, overrides, parse_err = fuzz(pages, fuzz_rounds)
        print(f"\n== fuzz: {fuzz_rounds} destructive mutations of {len(pages)} real pages ==")
        show("chrome rules under mutation", total)
        print(f"  tightening fired: {tight}   relaxed pass used: {relaxed}")
        print(f"  root-override fired: {overrides}   parse_error caught: {parse_err}")


if __name__ == "__main__":
    main()
