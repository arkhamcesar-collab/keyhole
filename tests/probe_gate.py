#!/usr/bin/env python
"""Feed the `trunc-root` gate a corpus nobody curated, and see if its margin holds.

The gate (``keyhole.ate_the_root``) says: chrome suppression ate the article when
it dropped more readable text from the content root than the result kept, and the
loss is bigger than an empty page. It was calibrated on the nine live pages of
``tests/probe_truncation.py`` — all chosen by me, and all developer sites. Nine
pages is a thin corpus for a threshold, and the pages are the shape I already
expect keyhole to handle, so the margin could be a fact about *my taste* rather
than about the web.

So this probe asks the question with the selection bias removed: the corpus is
chosen by somebody else. Hacker News' and Lobsters' front pages are today's links,
picked by strangers; the Wikipedia articles come from ``list=random``, i.e. a die
roll. I do not get to leave out the page that would have broken the gate — which
is the only way a threshold calibrated on nine pages can be checked at all.

Per page it prints the same two numbers the gate itself reads, from the shipped
reader (``probe_truncation.measure``, not a model of it):

    ratio   share of the root's readable text suppression threw away
    rung    what the shipped ladder did about it

and the result that matters is ``gate would eat`` — an honest, live page on which
``ate_the_root`` is true. Under the gate's own theory that is a false positive:
the page is fine and the tool would ship it relaxed and label it truncated. Zero
means the margin survived contact with a corpus I did not pick.

Pages that can't be measured are named, not dropped: a bot wall, a 403, a PDF and
a page with no content root at all are all *no evidence*, and folding them into a
total would be the empty-success shape this whole project is about.

Run:  python tests/probe_gate.py [path/to/urls.tsv] [--min-chars N]
"""
import importlib.util
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402

DEFAULT_LIST = os.path.join(HERE, "tests", "corpus", "gate_urls.txt")
OUT = os.path.join(HERE, "tests", "corpus", "gate_measured.json")

# A page whose extracted text is this small tells us nothing about a share: the
# gate's own floor (keyhole.EMPTY_TEXT) already refuses to judge them.
MIN_CHARS = 200


def _load_sibling(name: str):
    """Load a sibling probe by path — the instrument is shared, not re-typed.

    ``measure`` and ``cached_download`` come from ``probe_truncation.py`` so this
    probe cannot drift from the one that calibrated the gate: it measures with
    the shipped ``_Reader`` and the shipped ``root_lost_share``, exactly as the
    gate does.
    """
    path = os.path.join(HERE, "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pt = _load_sibling("probe_truncation")
measure = _pt.measure
cached_download = _pt.cached_download


def read_list(path: str) -> list[tuple[str, str]]:
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            src, _, url = line.partition("\t")
            out.append((src, url if url else src))
    return out


def is_html(u: str) -> bool:
    """Only HTML pages belong in this measurement: the gate reads a DOM."""
    low = u.lower()
    if low.endswith(".pdf"):
        return False
    return not any(h in low for h in ("twitter.com", "x.com/", "youtube.com",
                                      "youtu.be", "bloomberg.com", "blob:"))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else DEFAULT_LIST
    floor = MIN_CHARS
    if "--min-chars" in sys.argv:
        floor = int(sys.argv[sys.argv.index("--min-chars") + 1])

    urls = read_list(path)
    gate = keyhole.ATE_ROOT
    print(f"keyhole {keyhole.__version__} — does the trunc-root gate hold on a "
          f"corpus I did not pick?\ncorpus: {path}  ({len(urls)} urls)\n")

    rows, skipped = [], []
    for src, url in urls:
        if not is_html(url):
            skipped.append((src, url, "not html"))
            continue
        try:
            html = cached_download(url)
        except Exception as e:
            skipped.append((src, url, f"{type(e).__name__}: {e}"[:70]))
            continue
        m = measure(html)
        rows.append({"src": src, "url": url, **{k: m[k] for k in
                    ("kept", "shipped", "drop_in_root", "drop_out_root",
                     "ratio", "ate", "scope", "rung")},
                     "by_label": m["by_label"]})

    print(f"{'src':<11} {'kept':>7} {'in_root':>8} {'ratio':>7} {'margin':>7}  rung / scope")
    print("-" * 78)
    for r in sorted(rows, key=lambda r: -r["ratio"]):
        rung = r["rung"] + (f"  {r['scope']}" if r["scope"] else "  scope=none")
        print(f"{r['src']:<11} {r['kept']:>7} {r['drop_in_root']:>8} "
              f"{r['ratio'] * 100:>6.1f}% {(gate - r['ratio']) * 100:>6.1f}%  {rung}")

    measured = [r for r in rows if r["kept"] >= floor]
    rooted = [r for r in measured if r["scope"]]
    ratios = [r["ratio"] for r in rooted]
    fired = [r for r in rows if r["ate"]]
    relaxed = [r for r in rows if r["rung"] != "strict"]

    print(f"\n== {len(rows)} pages downloaded, {len(measured)} with >= {floor} "
          f"kept chars")
    if ratios:
        ratios.sort()
        q = statistics.quantiles(ratios, n=4) if len(ratios) > 3 else ratios
        print(f"   rooted pages (gate has a region to judge): {len(rooted)}")
        print(f"   ratio:  max {max(ratios) * 100:.1f}%   p75 {q[2] * 100:.1f}%   "
              f"median {statistics.median(ratios) * 100:.1f}%")
        above = [r for r in rooted if r["ratio"] > 0.25]
        print(f"   pages above 25% (npm, the worst of the old nine): "
              f"{len(above)}" + (f" -> {[r['url'].split('/')[2] for r in above]}" if above else ""))
        worst = max(rooted, key=lambda r: r["ratio"])
        print(f"\n   worst honest page: {worst['ratio'] * 100:.1f}%  "
              f"{worst['kept']:,} kept, {worst['drop_in_root']:,} dropped in root")
        print(f"     {worst['url']}")
        for label, chars in sorted(worst["by_label"].items(), key=lambda kv: -kv[1])[:3]:
            print(f"       ↳ {chars:>7}  {label}")
    else:
        print("   no rooted page survived the floor: the corpus says nothing "
              "about the gate")

    print(f"\n== ladder behaviour on the honest web")
    print(f"   parse=strict (no rung fired):        {len(rows) - len(relaxed)}")
    print(f"   relaxed:                             {len(relaxed)}"
          + (f"  {sorted({r['rung'] for r in relaxed})}" if relaxed else ""))
    print(f"   GATE WOULD EAT (false positives):    {len(fired)}"
          + ("  <-- the margin did not survive" if fired else "  (margin held)"))
    for r in fired:
        print(f"     {r['url']}  ratio {r['ratio'] * 100:.0f}%  "
              f"kept {r['kept']:,}  in_root {r['drop_in_root']:,}")

    print(f"\n== not measured ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<11} {why:<38} {url}")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"gate": gate, "floor": floor, "measured": rows,
                   "skipped": [{"src": s, "url": u, "why": w} for s, u, w in skipped]},
                  fh, indent=1)
    print(f"\nrecorded: {os.path.relpath(OUT, HERE)}")


if __name__ == "__main__":
    main()
