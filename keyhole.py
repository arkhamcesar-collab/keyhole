#!/usr/bin/env python
"""Keyhole — fetch the pages other tools can't.

Most fetchers fail two ways: they get blocked by a bot wall and return a 403 the
caller has to decode, or they succeed and hand back 9,000 characters of nav and
cookie-banner soup. Keyhole does neither. It:

  1. fetches with a browser-realistic header set (the single fix for the most
     common wall: Cloudflare's "error code: 1010" on a default User-Agent),
  2. CLASSIFIES a wall when it hits one, naming it instead of returning HTML,
  3. converts real content to clean markdown, dropping chrome/nav/footer/script,
  4. can escalate to a real browser for JS-rendered or JS-challenge pages.

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
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser

__version__ = "0.1.1"

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
        res.markdown = html_to_markdown(body)
        res.text = html_to_text(body)
        res.links = extract_links(body, res.final_url or url)
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


class _Reader(HTMLParser):
    """Single pass: markdown, plain text, title/description, links.

    Uses an explicit tag stack rather than depth counters. Counters desynchronise
    the moment a document has an unbalanced or void tag — and then silently drop
    the remainder of the page. Tolerance here has to be structural, not hoped for.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.md: list[str] = []
        self.txt: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.title = ""
        self.description = ""
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

    def _push(self, tag, suppress, prefix=None):
        self._stack.append((tag, suppress))
        if not suppress and prefix:
            self.md.append(prefix)

    # -- parser
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = self._attrs(attrs)

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


def _reader(html_text: str, cls=None) -> _Reader:
    p = (cls or _Reader)()
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
    """Parse strictly; if that yields nothing, parse again without chrome detection.

    Suppression is heuristic and best-effort. Malformed HTML (a sidebar opened
    once and never closed) or an over-eager class pattern can nest an entire
    document inside a suppressed subtree. Returning an empty result for a page
    that plainly has text is a worse failure than keeping a cookie banner.
    """
    p = _reader(html_text)
    if p.md or p.txt or p.links:
        return p
    return _reader(html_text, _NoChromeReader)


def html_to_markdown(html_text: str) -> str:
    md = "".join(_parse(html_text).md)
    md = re.sub(r"[ \t]+", " ", md)
    md = re.sub(r" *\n *", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def html_to_text(html_text: str) -> str:
    return re.sub(r"\s+", " ", " ".join(_parse(html_text).txt)).strip()


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


def extract_links(html_text: str, base: str = "") -> list:
    out, seen = [], set()
    for label, href in _parse(html_text).links:
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
    res.markdown = html_to_markdown(dom)
    res.text = html_to_text(dom)
    res.links = extract_links(dom, url)
    if classify_wall(200, dom, {}):
        res.wall = {"kind": "post_render", "why": "the page is still gated after rendering"}
    return res


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
        print(f"bytes: {res.bytes_in}  links: {len(res.links)}  text: {len(res.text)}  method: {res.method}")
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
    args = ap.parse_args(argv)
    if args.chrome:
        CHROME_EXE_CANDIDATES.insert(0, args.chrome)
    if args.cmd == "fetch":
        res = fetch(args.url, timeout=args.timeout)
        # A client-rendered shell is HTTP 200 carrying almost no text, so
        # res.ok alone must not veto rendering: --render means render.
        shell = (res.status == 200 and not res.error and res.bytes_in > 0
                 and len(res.text or "") < 200)
        if args.render and (res.wall or not res.ok or shell):
            ren = render(res.final_url or res.url)
            if ren.status == 200 and not ren.error:
                res = ren
            elif ren.error:
                res.error = f"{res.error + '; ' if res.error else ''}{ren.error}"
        _emit(res, args)
        return 0 if res.ok else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
