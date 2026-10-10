#!/usr/bin/env python
"""Does the paragraph-tightening rule ever lose text or grow a page?

Runs each page twice through keyhole's own extractor: once as shipped, once with
the tightening disabled by monkeypatch. Prints the delta and whether the article
marker survives both ways. The rule's promise is narrow — it may only shrink, and
it may never drop the article — so a positive delta or a lost marker is a bug.

    python tests/probe_tighten.py
"""
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402

SITES = [
    ("wikipedia", "https://en.wikipedia.org/wiki/Cloudflare", "is an American technology company"),
    ("wiki/PL", "https://en.wikipedia.org/wiki/Python_(programming_language)", "is a high-level"),
    ("mdn", "https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS", "Cross-Origin Resource Sharing"),
    ("mdn/css", "https://developer.mozilla.org/en-US/docs/Web/CSS/grid", "CSS grid layout"),
    ("npm", "https://www.npmjs.com/package/react", "React"),
    ("peps", "https://peps.python.org/pep-0008/", "Style Guide"),
    ("docs.py", "https://docs.python.org/3/library/html.parser.html", "HTMLParser"),
    ("github", "https://github.com/psf/requests", "Requests"),
    ("blog", "https://blog.rust-lang.org/", "Rust"),
    ("example", "https://example.com", "This domain is for use in"),
    ("hn", "https://news.ycombinator.com/news", "Hacker News"),
]

_orig_tightest = keyhole._Reader._tightest


def raw_html(url):
    req = urllib.request.Request(url, headers=dict(keyhole.BROWSER_HEADERS))
    with urllib.request.urlopen(req, timeout=25) as r:
        return keyhole._decompress(r.read(), r.headers.get("Content-Encoding", "")).decode("utf-8", "replace")


def main():
    bad = 0
    print(f"keyhole {keyhole.__version__} — tighten on vs off\n")
    for name, url, marker in SITES:
        try:
            html = raw_html(url)
        except Exception as e:
            print(f"{name:10} FETCH FAILED: {type(e).__name__}: {e}")
            continue
        keyhole._Reader._tightest = lambda *a: None
        off = keyhole.analyze(html)
        off_scope, off_text = off.scope or "none", keyhole._text_of(off)
        keyhole._Reader._tightest = _orig_tightest
        on = keyhole.analyze(html)
        on_scope, on_text = on.scope or "none", keyhole._text_of(on)
        delta = len(on_text) - len(off_text)
        m_off, m_on = marker in off_text, marker in on_text
        flag = ""
        if delta > 0:
            flag, bad = "  <-- GREW", bad + 1
        if m_off and not m_on:
            flag, bad = "  <-- LOST THE ARTICLE", bad + 1
        print(f"{name:10} off={len(off_text):>7} ({off_scope:<24}) "
              f"on={len(on_text):>7} ({on_scope:<24}) d={delta:+7} "
              f"marker={'Y' if m_on else 'N'} (was {'Y' if m_off else 'N'}){flag}")
    keyhole._Reader._tightest = _orig_tightest
    print(f"\n{'OK — nothing grew, nothing lost the marker' if not bad else f'{bad} REGRESSION(S)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
