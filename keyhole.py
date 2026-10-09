#!/usr/bin/env python
"""Keyhole — fetch the pages other tools can't.

Most fetchers fail two ways: they get blocked by a bot wall and return a 403 the
caller has to decode, or they succeed and hand back 9,000 characters of nav and
cookie-banner soup. Keyhole does neither. It:

  1. fetches with a browser-realistic header set (the single fix for the most
     common wall: Cloudflare's "error code: 1010" on a default User-Agent),
  2. CLASSIFIES a wall when it hits one, naming it instead of returning HTML,
  3. converts real content to clean markdown, dropping chrome/nav/footer/script,
  4. scopes that content to the page's own root (<main>, role="main", <article>)
     and says which root it used, or that it found none,
  5. can escalate to a real browser for JS-rendered or JS-challenge pages.

Stdlib only — no install step, runs anywhere Python does.

  ./keyhole.py fetch https://example.com
  ./keyhole.py fetch https://example.com --md
  ./keyhole.py fetch https://example.com --json
  ./keyhole.py fetch https://example.com --render      # escalate to browser
"""
from __future__ import annotations

import argparse
import gzip
import html as html_mod
import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser

__version__ = "0.4.0"

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "close",
}

# Ordered: first match wins. Each is (kind, human explanation, regex).
WALL_SIGNATURES = [
    ("cloudflare_1010", "Cloudflare rejected the client fingerprint (error 1010). "
                        "Almost always a missing/plain User-Agent.",
     r"error code:?\s*1010"),
    ("cloudflare_challenge", "Cloudflare interstitial JS challenge — needs a real browser to pass.",
     r"just a moment|cf-browser-verification|cf_chl_|challenge-platform|enable javascript and cookies to continue"),
    ("cloudflare_block", "Cloudflare hard block (1020/attention required).",
     r"attention required|error code:?\s*10(20|15|29)|you have been blocked"),
    ("akamai", "Akamai bot manager interstitial.", r"akamai.*(bot|reference)|_abck"),
    ("datadome", "DataDome bot wall.", r"datadome|dd_cookie|blocked because we believe"),
    ("perimeterx", "PerimeterX / HUMAN bot wall.", r"perimeterx|px-captcha|_pxhd"),
    ("captcha", "Interactive CAPTCHA required.", r"g-recaptcha|hcaptcha|cf-turnstile"),
    ("js_required", "Page is a JS shell; content needs rendering.", r"<noscript>[^<]*enable javascript"),
    ("consent_gate", "Blocked by a consent/paywall gate.", r"cookie consent|accept all cookies|subscribe to continue"),
]

CHROME_EXE_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def _decompress(raw: bytes, encoding: str) -> bytes:
    enc = (encoding or "").lower()
    try:
        if "gzip" in enc:
            return gzip.decompress(raw)
        if "deflate" in enc:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
    except Exception:
        return raw
    return raw


def classify_wall(status: int, body: str, headers: dict) -> tuple[str, str] | None:
    """Return (kind, explanation) if this response is a bot wall, else None."""
    # A 200 with a substantial body IS the page. Walls replace content; they do
    # not accompany it. Without this guard, Wikipedia gets flagged as a CAPTCHA
    # because its HTML contains a reCAPTCHA form.
    if status == 200 and len(body) > 20000:
        return None
    probe = body[:20000].lower()
    for kind, why, pattern in WALL_SIGNATURES:
        if re.search(pattern, probe, re.I):
            return kind, why
    if status in (403, 429, 503) and len(body) < 3000:
        srv = (headers.get("Server") or "").lower()
        return ("http_%d" % status,
                f"HTTP {status} with a tiny body{'(Server: %s)' % srv if srv else ''} — "
                "looks like a deliberate block rather than a real page.")
    return None


@dataclass
class Result:
    url: str
    final_url: str = ""
    status: int = 0
    method: str = "http"
    content_type: str = ""
    title: str = ""
    description: str = ""
    text: str = ""
    markdown: str = ""
    links: list = field(default_factory=list)
    scope: str = ""      # content root the extraction was scoped to; "" = whole page
    bytes_in: int = 0
    wall: dict | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200 and not self.wall and not self.error


def fetch(url: str, timeout: float = 25.0, headers: dict | None = None,
          allow_walls: bool = True) -> Result:
    """Fetch a URL with browser-realistic headers. Never raises for HTTP errors."""
    res = Result(url=url)
    if not urllib.parse.urlparse(url).scheme:
        url = "https://" + url
        res.url = url
    hdrs = dict(BROWSER_HEADERS)
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            res.status = r.status
            res.final_url = r.geturl()
            res.content_type = r.headers.get("Content-Type", "")
            res.bytes_in = len(raw)
            body = _decompress(raw, r.headers.get("Content-Encoding", "")).decode("utf-8", "replace")
            hdrs_out = {k: v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        res.status = e.code
        res.final_url = getattr(e, "url", url)
        res.content_type = (e.headers.get("Content-Type", "") if e.headers else "")
        res.bytes_in = len(raw)
        body = _decompress(raw, (e.headers.get("Content-Encoding", "") if e.headers else "")).decode("utf-8", "replace")
        hdrs_out = {k: v for k, v in (e.headers.items() if e.headers else [])}
    except Exception as e:
        res.error = f"{type(e).__name__}: {e}"
        return res

    wall = classify_wall(res.status, body, hdrs_out)
    if wall:
        res.wall = {"kind": wall[0], "why": wall[1]}
        if not allow_walls:
            return res

    if "html" in res.content_type.lower() or body.lstrip()[:1] == "<":
        meta = extract_metadata(body)
        res.title = meta["title"]
        res.description = meta["description"]
        page = analyze(body)
        res.markdown = _markdown_of(page)
        res.text = _text_of(page)
        res.links = _links_from(page, res.final_url or url)
        res.scope = page.scope
    else:
        res.text = body
        res.markdown = body
    return res


# ---------------------------------------------------------------- HTML parsing

# Dropped entirely: never contribute text, never nest content.
_DROP_TAGS = {"script", "style", "noscript", "svg", "head", "template", "iframe", "canvas"}
# No end tag in HTML; must never be pushed onto the nesting stack.
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
              "link", "meta", "param", "source", "track", "wbr"}
# Suppressed as page chrome. Deliberately narrow — only patterns that are almost
# never real content, so a product description can't be eaten by a class name.
_CHROME_PATTERNS = re.compile(
    r"\b(cookie[-_]?(banner|consent|notice|bar)|site[-_]?nav|navbar|main[-_]?menu|"
    r"breadcrumb|skip[-_]?link|social[-_]?(share|icons)|newsletter|"
    r"advert(isement)?|sponsored|promo[-_]?banner|sidebar)\b", re.I)
_CHROME_TAGS = {"nav", "footer", "aside"}
# Where real content starts. <main> is unique per spec; <article> is not, but a
# page whose first article comes after a language switcher wants the same cut.
_ROOT_TAGS = {"main", "article"}


class _Reader(HTMLParser):
    """Single pass: markdown, plain text, title/description, links, content scope.

    Uses an explicit tag stack rather than depth counters. Counters desynchronise
    the moment a document has an unbalanced or void tag — and then silently drop
    the remainder of the page. Tolerance here has to be structural, not hoped for.

    Everything is accumulated in document order, and *afterwards* the region
    before the content root is discarded (see _apply_scope). Slicing at the end
    instead of buffering as we go is what keeps the failure mode honest: when the
    chosen root turns out to hold nothing, the untouched document is still there
    to fall back on. ``self.scope`` names the root actually used, so a caller can
    tell "scoped to <main>" from "no root found, kept the whole page" — a
    scoping that silently did nothing would be indistinguishable from one that
    silently dropped the article.
    """

    def __init__(self, scope: bool = True):
        super().__init__(convert_charrefs=True)
        self.md: list[str] = []
        self.txt: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.title = ""
        self.description = ""
        self.scope = ""                     # content root used, "" = whole document
        self._want_scope = scope
        self._root_at: tuple[int, int, int] | None = None   # (md, txt, links) cut
        self._root_tag = ""
        self._stack: list[tuple[str, bool]] = []   # (tag, suppressed)
        self._in_title = False
        self._cur_link: str | None = None
        self._link_text: list[str] = []
        self._list_depth = 0
        self._pre_depth = 0

    # -- helpers
    @staticmethod
    def _attrs(attrs):
        return {k.lower(): (v or "") for k, v in attrs}

    def _suppressed(self) -> bool:
        return any(s for _, s in self._stack)

    # Structural tags are never chrome: suppressing one of these hides an entire
    # page. Wikipedia's <html> carries a class containing "main-menu", which is
    # how a 320KB article once parsed down to zero characters.
    _NEVER_CHROME = frozenset({"html", "body", "main", "article", "center"})
    # Class-name heuristics only apply to containers that plausibly ARE chrome.
    _CLASS_CHECK_TAGS = frozenset({"div", "aside", "section", "header", "footer",
                                   "ul", "ol", "form", "span", "p", "nav", "table"})

    @staticmethod
    def _is_chrome(tag: str, a: dict) -> bool:
        if tag in _Reader._NEVER_CHROME:
            return False
        if tag in _CHROME_TAGS:
            return True
        if a.get("role") in ("navigation", "banner", "contentinfo", "complementary"):
            return True
        if a.get("aria-hidden") == "true":
            return True
        if tag not in _Reader._CLASS_CHECK_TAGS:
            return False
        return bool(_CHROME_PATTERNS.search(f"{a.get('id', '')} {a.get('class', '')}"))

    # -- content scope
    @staticmethod
    def _content_root(tag: str, a: dict) -> str:
        """Name the content root this tag opens, or "" if it opens none."""
        if tag in _ROOT_TAGS:
            return tag
        if a.get("role") == "main":
            return f"{tag}[role=main]"
        return ""

    _ROOT_STRENGTH = {"article": 1, "main": 2}

    def _adopt_root(self, tag: str, a: dict) -> None:
        """Remember where the content starts; a stronger root overrides a weaker.

        <main> beats <article>, so a teaser article above the real <main> doesn't
        win the cut just by coming first.
        """
        if not self._want_scope:
            return
        name = self._content_root(tag, a)
        if not name:
            return
        rank = self._ROOT_STRENGTH.get(name.split("[")[0], 2)
        if self._root_at is not None:
            if rank <= self._ROOT_STRENGTH.get(self._root_tag.split("[")[0], 2):
                return
        self._root_at = (len(self.md), len(self.txt), len(self.links))
        self._root_tag = name
        self.scope = name

    def _apply_scope(self) -> None:
        """Drop everything before the content root — but never at the cost of it all.

        If the chosen root holds no markdown, no text and no links, the cut is
        abandoned and the whole document is kept, and ``scope`` goes back to ""
        so nobody reads a scoping that never happened.
        """
        if self._root_at is None:
            return
        cut_md, cut_txt, cut_links = self._root_at
        if "".join(self.md[cut_md:]).strip() or self.txt[cut_txt:] or self.links[cut_links:]:
            del self.md[:cut_md]
            del self.txt[:cut_txt]
            del self.links[:cut_links]
        else:
            self.scope = ""
            self._root_at = None

    def close(self):
        super().close()
        self._apply_scope()

    def _push(self, tag, suppress, prefix=None):
        self._stack.append((tag, suppress))
        if not suppress and prefix:
            self.md.append(prefix)

    # -- parser
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = self._attrs(attrs)
        self._adopt_root(tag, a)

        if tag == "title":
            self._in_title = True
        if tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name in ("description", "og:description") and not self.description:
                self.description = a.get("content", "").strip()
            if name == "og:title" and not self.title:
                self.title = a.get("content", "").strip()

        suppress = self._suppressed() or tag in _DROP_TAGS or self._is_chrome(tag, a)

        if tag in ("ul", "ol"):
            self._list_depth += 1

        if tag in _VOID_TAGS:
            # No end tag is coming: render the effect, push nothing.
            if not suppress:
                if tag == "br":
                    self.md.append("\n")
                elif tag == "hr":
                    self.md.append("\n---\n")
                elif tag == "img":
                    alt = a.get("alt", "").strip()
                    if alt:
                        self.md.append(f"![{alt}]()")
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._push(tag, suppress, "\n" + "#" * int(tag[1]) + " ")
        elif tag == "p":
            self._push(tag, suppress, "\n\n")
        elif tag == "li":
            self._push(tag, suppress, "\n" + "  " * max(0, self._list_depth - 1) + "- ")
        elif tag in ("ul", "ol"):
            self._push(tag, suppress)
        elif tag in ("strong", "b"):
            self._push(tag, suppress, "**")
        elif tag in ("em", "i"):
            self._push(tag, suppress, "*")
        elif tag == "code" and not self._pre_depth:
            self._push(tag, suppress, "`")
        elif tag == "pre":
            self._pre_depth += 1
            self._push(tag, suppress, "\n```\n")
        elif tag == "blockquote":
            self._push(tag, suppress, "\n> ")
        elif tag in ("td", "th"):
            self._push(tag, suppress, " | ")
        elif tag == "a":
            self._push(tag, suppress)
            href = a.get("href", "")
            if not suppress and href and not href.lower().startswith(("javascript:", "#")):
                self._cur_link = href
                self._link_text = []
        else:
            self._push(tag, suppress)

    def handle_startendtag(self, tag, attrs):
        # Self-closing: render the effect, leave the stack balanced.
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()

        # Unwind to the matching open tag; tolerate missing and interleaved tags.
        idx = None
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                idx = i
                break
        if idx is None:
            if tag == "title":
                self._in_title = False
            return
        suppressed = self._stack[idx][1]
        del self._stack[idx:]

        if tag in ("ul", "ol"):
            self._list_depth = max(0, self._list_depth - 1)
        if tag == "title":
            self._in_title = False

        if suppressed or self._suppressed():
            if tag == "a":
                self._cur_link = None
                self._link_text = []
            return

        if tag == "a":
            label = " ".join("".join(self._link_text).split())
            if label and self._cur_link:
                self.links.append((label, self._cur_link))
            self._cur_link = None
            self._link_text = []
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "section",
                     "article", "blockquote", "table", "tr", "main", "ul", "ol"):
            self.md.append("\n")
        elif tag in ("strong", "b"):
            self.md.append("**")
        elif tag in ("em", "i"):
            self.md.append("*")
        elif tag == "code" and not self._pre_depth:
            self.md.append("`")
        elif tag == "pre":
            self._pre_depth = max(0, self._pre_depth - 1)
            self.md.append("\n```\n")

    def handle_data(self, data):
        if self._in_title:
            self.title = f"{self.title} {data}".strip() if self.title else data.strip()
        if self._suppressed():
            return
        if self._cur_link is not None:
            self._link_text.append(data)
        if not data.strip():
            if self.md and not self.md[-1].endswith((" ", "\n")):
                self.md.append(" ")
            return
        self.md.append(data)
        self.txt.append(data)


def _reader(html_text: str, cls=None, scope: bool = True) -> _Reader:
    p = (cls or _Reader)(scope=scope)
    try:
        p.feed(html_text)
        p.close()
    except Exception:
        pass
    return p


class _NoChromeReader(_Reader):
    """Fallback pass with chrome detection disabled. See _parse()."""

    @staticmethod
    def _is_chrome(tag, a):
        return False


def _parse(html_text: str) -> _Reader:
    """Parse strictly; on an empty result relax the heuristics, twice if needed.

    Both suppression and content scoping are best-effort. Malformed HTML (a
    sidebar opened once and never closed) or an over-eager class pattern can nest
    an entire document inside a suppressed subtree; a self-contained <main> can
    hold the wrapper and not the words. Returning an empty result for a page that
    plainly has text is a worse failure than keeping a cookie banner or a
    language switcher, so the ladder ends with no heuristics at all.
    """
    p = _reader(html_text)
    if p.md or p.txt or p.links:
        return p
    p = _reader(html_text, _NoChromeReader)
    if p.md or p.txt or p.links:
        return p
    return _reader(html_text, _NoChromeReader, scope=False)


def analyze(html_text: str) -> _Reader:
    """One parse of a document: markdown, text, links, and the scope used.

    `fetch` goes through here so a page is parsed once instead of three times, and
    so `Result.scope` can say which content root the output came from.
    """
    return _parse(html_text)


def _markdown_of(r: _Reader) -> str:
    md = "".join(r.md)
    md = re.sub(r"[ \t]+", " ", md)
    md = re.sub(r" *\n *", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def _text_of(r: _Reader) -> str:
    return re.sub(r"\s+", " ", " ".join(r.txt)).strip()


def html_to_markdown(html_text: str) -> str:
    return _markdown_of(_parse(html_text))


def html_to_text(html_text: str) -> str:
    return _text_of(_parse(html_text))


def extract_metadata(html_text: str) -> dict:
    # Title/description are captured before suppression is evaluated, so the
    # strict pass is sufficient here.
    r = _reader(html_text)
    title = r.title.strip()
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.S | re.I)
        title = html_mod.unescape(m.group(1)).strip() if m else ""
    desc = r.description.strip()
    if not desc:
        m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', html_text, re.I)
        desc = html_mod.unescape(m.group(1)).strip() if m else ""
    return {"title": re.sub(r"\s+", " ", title), "description": desc[:500]}


def _links_from(r: _Reader, base: str = "") -> list:
    out, seen = [], set()
    for label, href in r.links:
        if not href:
            continue
        absolute = urllib.parse.urljoin(base, href) if base else href
        if not absolute.startswith(("http://", "https://")):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append({"text": label[:160], "url": absolute})
        if len(out) >= 60:
            break
    return out


def extract_links(html_text: str, base: str = "") -> list:
    return _links_from(_parse(html_text), base)


# ------------------------------------------------------------ browser fallback

def find_chrome() -> str | None:
    for c in CHROME_EXE_CANDIDATES:
        if os.path.exists(c):
            return c
        found = shutil.which(c)
        if found:
            return found
    return None


def render(url: str, timeout: int = 40) -> Result:
    """Escalate to a real browser via headless Chrome --dump-dom.

    Passes JS challenges that plain HTTP can't, at the cost of a browser launch.
    A missing Chrome binary is reported as an error, never as content.
    """
    res = Result(url=url, method="browser")
    chrome = find_chrome()
    if not chrome:
        res.error = "no Chrome binary found (set --chrome PATH)"
        return res
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--virtual-time-budget=8000", "--dump-dom", url]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        res.error = f"browser render timed out after {timeout}s"
        return res
    except Exception as e:
        res.error = f"{type(e).__name__}: {e}"
        return res
    dom = proc.stdout.decode("utf-8", "replace")
    if not dom.strip():
        res.error = "browser returned an empty DOM"
        return res
    res.status = 200
    res.final_url = url
    res.content_type = "text/html (rendered)"
    res.bytes_in = len(dom)
    meta = extract_metadata(dom)
    res.title, res.description = meta["title"], meta["description"]
    page = analyze(dom)
    res.markdown = _markdown_of(page)
    res.text = _text_of(page)
    res.links = _links_from(page, url)
    res.scope = page.scope
    if classify_wall(200, dom, {}):
        res.wall = {"kind": "post_render", "why": "the page is still gated after rendering"}
    return res


# ------------------------------------------------------------------- batching

def parse_url_list(text: str) -> list:
    """URLs from a text blob: one per line, blanks and '#'-comment lines dropped,
    duplicates removed keeping the first occurrence, input order preserved.

    '#' is NOT an inline comment marker here. URLs legitimately carry fragments
    (``https://x.dev/a#section``), and silently truncating one would fetch the
    wrong page rather than fail — a lie is worse than an error.
    """
    out, seen = [], set()
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def fetch_maybe_render(url: str, timeout: float = 25.0, do_render: bool = False) -> Result:
    """``fetch()``, escalating to a real browser when asked and the HTTP result is
    unusable: walled, errored, or a client-rendered shell.

    A shell — HTTP 200 carrying almost no text — must escalate even though
    ``res.ok`` is True, so ``ok`` alone cannot be the gate. If the escalation
    itself fails, the error is appended rather than swallowed: an empty render is
    never allowed to look like content.
    """
    res = fetch(url, timeout=timeout)
    shell = (res.status == 200 and not res.error and res.bytes_in > 0
             and len(res.text or "") < 200)
    if do_render and (res.wall or not res.ok or shell):
        ren = render(res.final_url or res.url)
        if ren.status == 200 and not ren.error:
            return ren
        if ren.error:
            res.error = f"{res.error + '; ' if res.error else ''}{ren.error}"
    return res


def _short(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1000:.1f}k"
    return str(n)


def format_batch_row(index: int, total: int, res: Result) -> str:
    """One line per URL. A wall and an error say so in the status column instead
    of being flattened into a generic failure — the whole point of the tool."""
    head = f"[{index}/{total}]"
    rendered = " [rendered]" if res.method == "browser" else ""
    if res.wall:
        return f"{head} WALL {res.wall['kind']:<22} {res.url}"
    if res.error:
        # URL first, reason on its own indented line: a 22-char grid cell cut the
        # actual error off mid-word, which is the least useful thing to truncate.
        return f"{head} ERR  {res.url}{rendered}\n            — {res.error[:140]}"
    if not res.ok:
        return f"{head} HTTP {res.status:<4} {'':<22}{res.url}"
    title = (res.title or "").strip()
    # scope=none means the page has no <main>/<article> and the whole document was
    # kept: the honest counterpart to a scope that silently did nothing.
    line = (f"{head} OK   text={_short(len(res.text or '')):<7} "
            f"links={len(res.links):<4} scope={res.scope or 'none':<12} "
            f"{res.url}{rendered}")
    return line + (f"\n            — {title[:80]}" if title else "")


def batch_payload(res: Result) -> dict:
    """The JSON view of a batch row: counts, not bodies. Batch surveys many URLs;
    shipping every page's text inline would defeat the point."""
    return {"url": res.url, "ok": res.ok, "status": res.status, "method": res.method,
            "final_url": res.final_url, "title": res.title, "bytes_in": res.bytes_in,
            "text_chars": len(res.text or ""), "links": len(res.links),
            "scope": res.scope, "wall": res.wall, "error": res.error}


# ---------------------------------------------------------------- corpus output

# Windows refuses these as file stems, in any case, with or without extension.
_WIN_RESERVED = frozenset({"con", "prn", "aux", "nul"}
                          | {f"com{i}" for i in range(1, 10)}
                          | {f"lpt{i}" for i in range(1, 10)})
_PAGE_EXTS = (".html", ".htm", ".xhtml", ".php", ".asp", ".aspx", ".jsp")
_SLUG_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def slug_for_url(url: str, max_len: int = 80) -> str:
    """A deterministic, filesystem-safe filename stem for a URL.

    host + path (plus query, which is identity for pages like ``?id=42``),
    lowercased with runs of unsafe characters collapsed to ``-``. The fragment
    is dropped: ``#section`` never reaches the server, so it names the same
    resource — and two URLs differing only by fragment collide, which
    :func:`corpus_filename` disambiguates rather than silently merging.

    The result is capped in length (Windows still counts characters in the full
    path) and never a reserved device name.
    """
    p = urllib.parse.urlparse(url if "//" in url else "https://" + url)
    host = (p.netloc or "url").lower()
    if host.startswith("www."):
        host = host[4:]
    host = host.split(":")[0]
    rest = p.path or ""
    for ext in _PAGE_EXTS:
        if rest.lower().endswith(ext):
            rest = rest[: -len(ext)]
            break
    if p.query:
        rest += "-" + p.query
    raw = (host + rest).strip("/")
    slug = _SLUG_UNSAFE.sub("-", raw).strip("-._").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    stem = slug[:max_len].strip("-._") or "index"
    if stem.split(".")[0] in _WIN_RESERVED:
        stem = "_" + stem
    return stem


def corpus_filename(url: str, taken: set) -> str:
    """Filename for one URL, unique within a batch.

    Collisions are resolved by input order (``-2``, ``-3``), so the same list
    always produces the same names — a re-run overwrites its own files instead
    of spraying ``-3``, ``-4`` duplicates.
    """
    stem = slug_for_url(url)
    name = f"{stem}.md"
    if name not in taken:
        taken.add(name)
        return name
    n = 2
    while f"{stem}-{n}.md" in taken:
        n += 1
    name = f"{stem}-{n}.md"
    taken.add(name)
    return name


def corpus_body(res: Result) -> str:
    """The markdown file for one result: a source line, then content or a named failure.

    A URL that came back walled or errored still gets a file. Skipping it would
    leave a corpus quietly missing the pages that most needed a human look — the
    silent-drop failure this tool exists to prevent. The file says ``FAILED`` and
    names the wall, so ``ls`` shows the hole instead of hiding it.
    """
    header = (f"<!-- source: {res.url}"
              + (" | rendered" if res.method == "browser" else "")
              + f" | scope: {res.scope or 'none (whole page)'} -->")
    if res.wall or res.error or not res.ok:
        reason = (f"WALL {res.wall['kind']}: {res.wall['why']}" if res.wall
                  else f"ERROR: {res.error}" if res.error
                  else f"HTTP {res.status}")
        return f"{header}\n# FAILED — {res.url}\n\n{reason}\n"
    parts = [header]
    title = (res.title or "").strip()
    body = (res.markdown or res.text or "").strip()
    # Only add the title if the extraction didn't already lead with a heading.
    if title and not re.match(r"#{1,2}\s", body):
        parts.append(f"# {title}")
    if body:
        parts.append(body)
    return "\n\n".join(parts) + "\n"


def write_corpus(results: list, outdir: str) -> list:
    """Write one ``.md`` per result into ``outdir``; return ``[(result, filename)]``."""
    os.makedirs(outdir, exist_ok=True)
    taken: set = set()
    written = []
    for res in results:
        name = corpus_filename(res.url, taken)
        with open(os.path.join(outdir, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(corpus_body(res))
        written.append((res, name))
    return written


def run_batch(urls: list, timeout: float = 25.0, do_render: bool = False,
              jobs: int = 4) -> list:
    """Fetch every URL, returning results in input order regardless of jobs.

    Order is the contract: a batch report that reordered itself by completion
    time would be unreadable next to the list you fed in. jobs is capped at 16 —
    beyond that the win is negligible and hammering a host is rude.
    """
    jobs = max(1, min(jobs, len(urls), 16))

    def one(u):
        return fetch_maybe_render(u, timeout=timeout, do_render=do_render)

    if jobs == 1:
        return [one(u) for u in urls]
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        return list(ex.map(one, urls))


# ------------------------------------------------------------------------ CLI

def _emit(res: Result, args) -> None:
    if args.json:
        payload = asdict(res)
        payload["ok"] = res.ok
        if not args.md:
            payload.pop("markdown", None)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if res.wall:
        print(f"WALL  {res.wall['kind']}", file=sys.stderr)
        print(f"      {res.wall['why']}", file=sys.stderr)
        print("      hint: retry with --render to escalate to a real browser", file=sys.stderr)
    if res.error:
        print(f"ERROR {res.error}", file=sys.stderr)
    if args.md and res.markdown:
        print(res.markdown)
    elif args.links:
        for l in res.links:
            print(f"{l['text'][:70]:70}  {l['url']}")
    elif not res.wall and not res.error:
        print(f"{res.status} {res.final_url}")
        if res.title:
            print(f"title: {res.title}")
        if res.description:
            print(f"desc:  {res.description[:200]}")
        print(f"bytes: {res.bytes_in}  links: {len(res.links)}  text: {len(res.text)}"
              f"  scope: {res.scope or 'none'}  method: {res.method}")
        if res.text[:200]:
            print(f"first: {res.text[:200]}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="keyhole", description="Fetch the pages other tools can't.")
    ap.add_argument("--version", action="version", version=f"keyhole {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="fetch a URL")
    f.add_argument("url")
    f.add_argument("--md", action="store_true", help="print clean markdown")
    f.add_argument("--json", action="store_true", help="print JSON")
    f.add_argument("--links", action="store_true", help="print extracted links")
    f.add_argument("--render", action="store_true", help="escalate to a real browser")
    f.add_argument("--timeout", type=float, default=25.0)
    f.add_argument("--chrome", default=None, help="path to a Chrome/Chromium binary")
    b = sub.add_parser("batch", help="fetch many URLs, one per line, from stdin or --file")
    b.add_argument("--file", default=None, help="read URLs from this file (default: stdin)")
    b.add_argument("--render", action="store_true", help="escalate unusable results to a browser")
    b.add_argument("--timeout", type=float, default=25.0)
    b.add_argument("--jobs", type=int, default=4, help="parallel fetches (default 4, capped at 16)")
    b.add_argument("--json", action="store_true", help="emit one JSON array instead of rows")
    b.add_argument("--out", default=None, metavar="DIR",
                   help="write one markdown file per URL into DIR (corpus builder)")
    args = ap.parse_args(argv)
    chrome = getattr(args, "chrome", None)
    if chrome:
        CHROME_EXE_CANDIDATES.insert(0, chrome)
    if args.cmd == "fetch":
        res = fetch_maybe_render(args.url, timeout=args.timeout, do_render=args.render)
        _emit(res, args)
        return 0 if res.ok else 1
    if args.cmd == "batch":
        if args.file:
            try:
                with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
                    raw = fh.read()
            except OSError as e:
                print(f"cannot read {args.file}: {e}", file=sys.stderr)
                return 2
        else:
            raw = sys.stdin.read()
        urls = parse_url_list(raw)
        if not urls:
            print("no URLs given — one per line on stdin, or --file PATH", file=sys.stderr)
            return 2
        results = run_batch(urls, timeout=args.timeout, do_render=args.render, jobs=args.jobs)
        written = write_corpus(results, args.out) if args.out else []
        names = {id(r): n for r, n in written}
        if args.json:
            print(json.dumps([batch_payload(r) for r in results], indent=2, ensure_ascii=False))
        else:
            for i, r in enumerate(results, 1):
                row = format_batch_row(i, len(results), r)
                if args.out:
                    row += f"\n            → {names[id(r)]}"
                print(row)
            note = f"{sum(1 for r in results if r.ok)}/{len(results)} ok"
            walled = sum(1 for r in results if r.wall)
            if walled:
                note += f", {walled} walled"
            if args.out:
                good = sum(1 for r, _ in written if r.ok)
                note += f", wrote {len(written)} files ({good} with content) to {args.out}"
            # Buffer order: without this the stderr summary can print before the
            # stdout rows it summarises, which reads as a contradiction.
            sys.stdout.flush()
            print(f"\n{note}", file=sys.stderr)
            if walled and not args.render:
                print("hint: --render to escalate the walled ones to a real browser", file=sys.stderr)
        return 0 if all(r.ok for r in results) else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
