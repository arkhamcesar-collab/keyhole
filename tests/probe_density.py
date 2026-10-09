#!/usr/bin/env python
"""Measure whether density-based content extraction would beat the current
<main>/<article> scope rule — before building it.

This is the discipline written down in THREADS.md: "deepest root wins" was
measured and discarded rather than built, so density gets the same treatment
before a line of it reaches keyhole.py.

The measurement has to use keyhole's *own* extractor, not a lookalike: comparing
a home-grown character count against keyhole's text length is exactly the
instrument that lies. So every candidate container is sliced out of the source
by character offset and run back through `keyhole.html_to_text`, and the result
is compared, like for like, against `keyhole.html_to_text` of the whole page.

Four candidate rules per URL:
  pick nonlink   tightest container holding ~all of the page's non-link text
                 (link-heavy chrome is mostly anchor text, so it inflates total
                 text without inflating non-link text),
  pick para      tightest container holding ~all of the page's <p> text
                 (the readability signal: prose lives in paragraphs),
  tighten *      the same two, but never above the structural root — density may
                 only remove chrome the rule cannot reach, never re-add chrome it
                 removed.

Each prints kept length, delta vs today, whether the article marker survives,
and the head, so the change is eyeballed rather than trusted.

    python tests/probe_density.py
"""
import os
import sys
import urllib.request
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402

DROP = {"script", "style", "noscript", "template", "svg", "head", "canvas", "iframe"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"}
CONTAINERS = {"div", "section", "article", "main", "td", "body"}


class Node:
    __slots__ = ("tag", "id", "cls", "parent", "children",
                 "total", "link", "para", "start", "end")

    def __init__(self, tag, id_, cls, parent, start):
        self.tag, self.id, self.cls, self.parent = tag, id_, cls, parent
        self.children = []
        self.total = 0
        self.link = 0
        self.para = 0
        self.start = start
        self.end = None

    @property
    def nonlink(self):
        return self.total - self.link

    def label(self):
        bits = [self.tag]
        if self.id:
            bits.append("#" + self.id)
        if self.cls:
            bits.append("." + self.cls.split()[0])
        return "".join(bits)


class Tree(HTMLParser):
    """Container tree with per-subtree text counts and source-character spans."""

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.html = html
        self.line_at = [0]
        for i, ch in enumerate(html):
            if ch == "\n":
                self.line_at.append(i + 1)
        self.root = Node("root", "", "", None, 0)
        self.stack = [self.root]
        self.a_depth = 0
        self.p_depth = 0
        self.suppress = 0

    def pos(self):
        line, col = self.getpos()
        return self.line_at[line - 1] + col if line - 1 < len(self.line_at) else 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        at = self.pos()
        if tag in DROP:
            self.suppress += 1
            return
        if tag in VOID:
            return
        if tag == "a":
            self.a_depth += 1
        if tag == "p":
            self.p_depth += 1
        a = {k.lower(): (v or "") for k, v in attrs}
        node = Node(tag, a.get("id", ""), a.get("class", ""), self.stack[-1], at)
        self.stack[-1].children.append(node)
        self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in DROP:
            if self.suppress:
                self.suppress -= 1
            return
        if tag in VOID:
            return
        if tag == "a" and self.a_depth:
            self.a_depth -= 1
        if tag == "p" and self.p_depth:
            self.p_depth -= 1
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack[i].end = self.pos()
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.suppress or not data:
            return
        is_link = self.a_depth > 0
        is_para = self.p_depth > 0
        for n in self.stack:
            n.total += len(data)
            if is_link:
                n.link += len(data)
            if is_para:
                n.para += len(data)

    def close(self):
        super().close()
        for n in self.stack:
            if n.end is None:
                n.end = len(self.html)


def walk(n):
    yield n
    for c in n.children:
        yield from walk(c)


def candidates(node):
    return [n for n in walk(node) if n.tag in CONTAINERS and n.total > 0]


def tightest(node, attr, cover=0.97):
    """Tightest container whose `attr` is >= cover of the max `attr` in `node`."""
    vals = [(n, getattr(n, attr)) for n in candidates(node)]
    M = max((v for _, v in vals), default=0)
    if not vals or M == 0:
        return None
    ok = [(n, v / M) for n, v in vals if v >= cover * M]
    return min(ok, key=lambda t: t[0].total)[0]


def scope_node(root):
    """The node the current rule cuts at: first <main>, else first <article>."""
    mains = [n for n in walk(root) if n.tag == "main"]
    if mains:
        return mains[0]
    arts = [n for n in walk(root) if n.tag == "article"]
    return arts[0] if arts else None


def ktext(node, html):
    """keyhole's own text of just this container, sliced from the source."""
    frag = html[node.start:node.end or len(html)]
    return keyhole.html_to_text(frag) if frag.strip() else ""


def raw_html(url):
    req = urllib.request.Request(url, headers=dict(keyhole.BROWSER_HEADERS))
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
        enc = r.headers.get("Content-Encoding", "")
        return keyhole._decompress(raw, enc).decode("utf-8", "replace")


SITES = [
    ("wikipedia", "https://en.wikipedia.org/wiki/Cloudflare",
     "is an American technology company"),
    ("mdn", "https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS",
     "Cross-Origin Resource Sharing"),
    ("npm", "https://www.npmjs.com/package/react", "React"),
    ("example", "https://example.com", "This domain is for use in"),
    ("hn", "https://news.ycombinator.com/news", "Hacker News"),
]


def row(name, label, node, node_name, today, marker, html):
    if node is None:
        print(f"  {label:16} {node_name:<24} -> none")
        return
    txt = ktext(node, html)
    delta = len(txt) - len(today)
    head = " ".join(txt[:64].split())
    print(f"  {label:16} {node_name:<24} len={len(txt):>7} ({delta:+6}) "
          f"m={'Y' if marker in txt else 'N'}  {head}")


def main():
    print(f"keyhole {keyhole.__version__} — density probe "
          f"(candidates run through keyhole's own extractor)\n")
    for name, url, marker in SITES:
        try:
            html = raw_html(url)
        except Exception as e:
            print(f"{name} FETCH FAILED: {type(e).__name__}: {e}\n")
            continue
        r = keyhole.analyze(html)
        today = keyhole._text_of(r)
        print(f"{name}  today scope={r.scope or 'none'}  len={len(today)}  "
              f"m={'Y' if marker in today else 'N'}")
        print(f"    today head: {' '.join(today[:70].split())}")
        tree = Tree(html)
        tree.feed(html)
        tree.close()

        w = tightest(tree.root, "nonlink")
        row(name, "pick nonlink", w, w.label() if w else "", today, marker, html)
        w = tightest(tree.root, "para")
        row(name, "pick para", w, w.label() if w else "", today, marker, html)

        sn = scope_node(tree.root)
        if sn is None:
            print(f"  {'tighten':16} {'no structural root':<24} -> (whole page kept)")
        else:
            for attr in ("nonlink", "para"):
                w = tightest(sn, attr)
                tag = f"root {sn.label()}" if w is sn else (w.label() if w else "none")
                row(name, "tighten " + attr, w, tag, today, marker, html)
        print()


if __name__ == "__main__":
    sys.exit(main())
