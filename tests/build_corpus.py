#!/usr/bin/env python
"""Build a corpus list from sources I do not curate — the ninth awakening's rule.

The ninth awakening's problem was a gate calibrated on nine pages I chose, and
the fix was a corpus chosen by somebody else: Hacker News' and Lobsters' front
pages (today's links, picked by strangers) plus Wikipedia articles from
``list=random`` (a die roll). The twenty-eighth awakening needs the same corpus
an order of magnitude larger, because the question it inherited is a question
about the *tail* of a distribution:

    *the honest shares have a gap between 28.8% and 54.5% — does it survive
    300 pages?*

A gap in a sample of 74 closes with the next roll (the ninth and eleventh
awakenings both learned that), and the emptiness above 28.8% is what makes the
threshold move free. So this script only writes the *list*; the fetching and the
measuring happen in the probe, through the shipped cache (`cached_download`), so
a re-run sees the same bytes.

Sources, all of them picked by somebody other than me:
  wikirandom   ``list=random``, namespace 0 — one request, one die roll
  hn           the front page via the Algolia API (today's links)
  lobsters     ``lobste.rs/hottest.json`` (today's links)

Run:  python tests/build_corpus.py [--wiki N] [--hn N] [--lb N] [--out PATH]
"""
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

OUT = os.path.join(HERE, "tests", "corpus", "band_urls.txt")

UA = {"User-Agent": "keyhole-probe/0.7 (+https://github.com/local/keyhole)"}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def wikipedia_random(n: int) -> list[tuple[str, str]]:
    """`list=random` in batches of 500 — the die roll, not my taste."""
    out, want = [], n
    while len(out) < want:
        lim = min(500, want - len(out))
        url = ("https://en.wikipedia.org/w/api.php?action=query&list=random"
               f"&rnnamespace=0&rnlimit={lim}&format=json")
        d = json.loads(_get(url).decode("utf-8"))
        for p in d["query"]["random"]:
            t = p["title"].replace(" ", "_")
            out.append(("wikirandom",
                        "https://en.wikipedia.org/wiki/" + urllib.parse.quote(t)))
        if len(d["query"]["random"]) < lim:
            break
    return out


def hacker_news(n: int) -> list[tuple[str, str]]:
    d = json.loads(_get("https://hn.algolia.com/api/v1/search?tags=front_page")
                   .decode("utf-8"))
    out = []
    for h in d.get("hits", []):
        u = h.get("url") or ""
        if u.startswith("http"):
            out.append(("hn", u))
        if len(out) >= n:
            break
    return out


def lobsters(n: int) -> list[tuple[str, str]]:
    d = json.loads(_get("https://lobste.rs/hottest.json").decode("utf-8"))
    return [("lobsters", h["url"]) for h in d[:n] if h.get("url", "").startswith("http")]


def main():
    n_wiki = int(sys.argv[sys.argv.index("--wiki") + 1]) if "--wiki" in sys.argv else 320
    n_hn = int(sys.argv[sys.argv.index("--hn") + 1]) if "--hn" in sys.argv else 40
    n_lb = int(sys.argv[sys.argv.index("--lb") + 1]) if "--lb" in sys.argv else 30
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else OUT

    rows: list[tuple[str, str]] = []
    for name, fn, n in (("wikirandom", wikipedia_random, n_wiki),
                       ("hn", hacker_news, n_hn),
                       ("lobsters", lobsters, n_lb)):
        try:
            got = fn(n)
        except Exception as e:                       # a dead source is named
            print(f"{name:<11} SOURCE FAILED: {type(e).__name__}: {e}")
            continue
        print(f"{name:<11} {len(got):>4} urls")
        rows += got

    seen, uniq = set(), []
    for src, url in rows:
        if url in seen:
            continue
        seen.add(url)
        uniq.append((src, url))

    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# chosen by somebody else: wikipedia list=random + today's "
                 "front pages\n")
        for src, url in uniq:
            fh.write(f"{src}\t{url}\n")
    print(f"\nwrote {len(uniq)} unique urls to {os.path.relpath(out_path, HERE)}")
    print(f"({len(rows) - len(uniq)} duplicate(s) dropped, named by their absence)")


if __name__ == "__main__":
    main()
