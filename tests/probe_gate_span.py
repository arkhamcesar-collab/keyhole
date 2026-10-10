#!/usr/bin/env python
"""Do the gate's numerator and denominator measure the same region?

``tests/probe_gate.py`` fed ``ate_the_root`` a corpus nobody curated and the gate
relaxed on two honest, live Wikipedia pages — on one of them it threw away a good
2,752-character article and shipped the chrome back with it. So the threshold is
being asked the wrong question, and this probe is about what the question is.

Two numbers go into the shipped share:

    sup_in_root   readable characters chrome suppression removed while the
                  <main> *frame* was open — the whole root region
    kept          characters the strict result actually returned — the span the
                  paragraph-tightening rule narrowed the root to (on Wikipedia,
                  ``main>div.mw-content-ltr``)

Those are two different regions, and dividing one by the other is how an honest
page reads as 61% eaten: Vector 2022 keeps the language switcher and the table of
contents inside ``<main>`` but *outside* the article container, so keyhole drops
them on purpose, excludes them from the result on purpose, and then counts them
as if it had lost article.

The fix is not a bigger threshold — it is to put the same region on both sides.
The candidate measured here compares what the two *passes* keep, both run through
the identical pipeline (same root, same tightening, same slicing), differing only
in whether chrome suppression is on:

    chrome_share = (kept_nochrome - kept_strict) / kept_nochrome

Text the no-chrome pass keeps and the strict pass drops is text suppression
removed from wherever the result actually came from — measured on output, not on
an internal counter, so the two sides of the division cannot be about different
places. The floor stays the same (``keyhole.EMPTY_TEXT``): a share on a stub is
still not a decision.

This probe prints the two candidates side by side over the honest corpus and,
with ``--fuzz``, over the same destructive mutations that calibrated the shipped
gate — because the cost of a narrower gate is exactly the silent truncations it
stops catching, and that number has to be measured, not argued.

Run:  python tests/probe_gate_span.py [--fuzz N] [urls.tsv] [--min-chars N]
"""
import importlib.util
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402
from keyhole import _NoChromeReader, _Reader  # noqa: E402

DEFAULT_LIST = os.path.join(HERE, "tests", "corpus", "gate_urls.txt")

# The three candidates for "the gate's numerator", scored identically everywhere.
# shipped = what keyhole tells you today; span = same region on both sides;
# para = the same region *and* the same cause (prose, not link labels).
CANDIDATES = ("shipped", "span", "para")


def _load_sibling(name: str):
    path = os.path.join(HERE, "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pg = _load_sibling("probe_gate")
_pr = _load_sibling("probe_rules")


class _ParaLoss(_Reader):
    """Chrome suppression that removed *paragraph* text inside the root.

    The whole exercise turned on one question the counter could not answer: on
    Torrebaja the strict result was complete — it ends in References and the stub
    note — yet suppression had removed 3,173 characters from the same container,
    because Wikipedia puts the municipality navbox and the authority-control block
    inside the article div. Chrome that lives inside the article container is
    still chrome, and counting it as lost article is the eighth awakening's sin
    in a new place: a counter that does not distinguish the cause.

    The discriminator is the one this project already uses twice (`<p>` text is
    what the tightening rule trusts, and it is what the density probe found
    survives). Prose is the article; a list of place names is not.

    **A `<p>` counts however it was opened.** This counter used to require
    ``self._para_depth`` — a `<p>` opened *before* the suppression, kept open
    across it. That reads only *inline* chrome (a citation bracket inside a
    paragraph) and is blind to *block* chrome that ate whole paragraphs (the
    navbox, the hatnote), because a `<p>` opened inside a suppressed frame never
    increments the shipped reader's depth counter. The tenth awakening found the
    same hole in ``probe_gate_pos`` and fixed it there with a suppression-scoped
    ``<p>`` depth; this row kept the blind condition for eleven awakenings. On the
    honest corpus the two conditions are not nested but *disjoint in part* —
    of 33,521 characters chrome removed from the root, the old condition reads
    2,690 (8.0%), the structural one 5,566 (16.6%), they share 1,937, and the
    union is 6,319 (18.9%): 3,629 the old row never saw, 753 it saw alone.
    """

    def __init__(self, scope: bool = True):
        super().__init__(scope)
        self.sup_para = 0
        self._sup_p = 0          # <p> open, inside the suppressed subtree

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        super().handle_starttag(tag, attrs)
        if tag == "p" and self._suppress_why() == "chrome":
            self._sup_p += 1

    def handle_endtag(self, tag):
        tag = tag.lower()
        suppressed_here = self._suppress_why() == "chrome"
        super().handle_endtag(tag)
        if tag == "p" and suppressed_here and self._sup_p:
            self._sup_p -= 1

    def handle_data(self, data):
        if (data.strip() and self._suppress_why() == "chrome"
                and self._in_root_region() and (self._para_depth or self._sup_p)):
            self.sup_para += len(data)
        super().handle_data(data)


def candidates(html: str) -> dict:
    """The shipped gate's numbers next to the same-region ones, per page."""
    m = _pg.measure(html)
    kept = m["kept"]
    nc = keyhole._reader(html, _NoChromeReader)
    kept_nc = len(keyhole._text_of(nc))
    lost = max(0, kept_nc - kept)          # what suppression cost the *result*
    para = keyhole._reader(html, _ParaLoss)
    return {
        "kept": kept,
        "kept_nc": kept_nc,
        "sup_in_root": m["drop_in_root"],
        "sup_para": para.sup_para,
        "shipped_share": m["ratio"],
        "shipped_fires": m["ate"],
        "span_share": (lost / kept_nc) if kept_nc else 0.0,
        "span_fires": lost > kept and lost > keyhole.EMPTY_TEXT,
        "span_lost": lost,
        "para_share": (para.sup_para / (kept + para.sup_para))
                      if (kept + para.sup_para) else 0.0,
        "para_fires": para.sup_para > kept and para.sup_para > keyhole.EMPTY_TEXT,
        "rung": m["rung"],
        "scope": m["scope"],
        "by_label": m["by_label"],
    }


def fuzz(pages, rounds, seed=0):
    """The mutations that calibrated the gate, scored by both candidates.

    ``missed`` is the number that fails: a mutation where the strict pass kept a
    minority of the article and the candidate stayed quiet — the silent
    truncation this whole exercise exists to stop.

    Read the ``shipped`` row with one caveat, measured in
    ``tests/probe_counts.py``: the truth here is ``any(candidate fires)`` and the
    shipped gate **is one of the candidates**, so this table grades three
    readings against a truth that one of them supplies. On the same mutations the
    audit names the cases where that truth calls a mutation real and the page
    says nothing was lost at all — and every candidate that stays quiet on one of
    those is charged a *miss* for text nobody lost. ``probe_gate_pos`` is the
    probe that grades against the page instead.
    """
    rnd = random.Random(seed)
    out = {k: {"missed": 0, "fires": 0} for k in CANDIDATES}
    out.update({"either_missed": 0, "both_clean": 0, "n": 0})
    for _ in range(rounds):
        src = rnd.choice(pages)
        anchors = [m for m in ("<main", "<article") if m in src]
        if rnd.random() < 0.75 and anchors:
            a = src.find(rnd.choice(anchors))
            a = src.find(">", a) + 1
            a = rnd.randrange(a, min(len(src), a + max(1, len(src) // 4)))
        else:
            a = rnd.randrange(len(src))
        rule = rnd.choice(['<div aria-hidden="true">', '<div role="navigation">',
                           '<aside>', '<nav>', '<div class="sidebar">',
                           '<div class="cookie-banner">'])
        cuts = rnd.randrange(1, 4)
        html = src[:a] + rule * cuts + src[a:]
        if rnd.random() < 0.3 and cuts > 1:
            html = html.replace("</div>", "", rnd.randrange(1, 3)) if "div" in rule else html
        try:
            c = candidates(html)
        except Exception:
            continue
        out["n"] += 1
        # ground truth: did the strict pass throw away the article? ask the passes
        # directly, with no counter in between.
        ate = any(c[f"{k}_fires"] for k in CANDIDATES)
        for k in CANDIDATES:
            if c[f"{k}_fires"]:
                out[k]["fires"] += 1
            elif ate:
                out[k]["missed"] += 1
        if not ate:
            out["both_clean"] += 1
        elif not all(c[f"{k}_fires"] for k in CANDIDATES):
            out["either_missed"] += 1
    return out


def main():
    rounds = 0
    if "--fuzz" in sys.argv:
        i = sys.argv.index("--fuzz")
        rounds = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 1500
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    args = [a for a in args if not a.isdigit()]
    path = args[0] if args else DEFAULT_LIST
    floor = keyhole.EMPTY_TEXT
    if "--min-chars" in sys.argv:
        floor = int(sys.argv[sys.argv.index("--min-chars") + 1])

    urls = _pg.read_list(path) + [(f"old-{n}", u) for n, u in
                                  [(s.replace(".", ""), u) for s, u in _pr.SITES]]
    print(f"keyhole {keyhole.__version__} — same region on both sides of the share?\n"
          f"corpus: {len(urls)} urls (uncurated + the nine the gate was built on)\n")

    rows, skipped = [], []
    for src, url in urls:
        if not _pg.is_html(url):
            skipped.append((src, url, "not html"))
            continue
        try:
            html = _pg.cached_download(url)
        except Exception as e:
            skipped.append((src, url, f"{type(e).__name__}"[:30]))
            continue
        c = candidates(html)
        if c["kept"] < floor or not c["scope"]:
            skipped.append((src, url, f"no region ({c['kept']} kept, scope {c['scope'] or 'none'})"))
            continue
        rows.append({"src": src, "url": url, **c})

    rows.sort(key=lambda r: -r["shipped_share"])
    print(f"{'src':<12} {'kept':>7} {'kc':>7} {'in_root':>8} {'in_para':>8} "
          f"{'shipped':>8} {'region':>8} {'para':>8}  fires")
    print("-" * 92)
    for r in rows:
        fires = ("S" if r["shipped_fires"] else "-") + ("R" if r["span_fires"] else "-") \
                + ("P" if r["para_fires"] else "-")
        print(f"{r['src']:<12} {r['kept']:>7} {r['kept_nc']:>7} {r['sup_in_root']:>8} "
              f"{r['sup_para']:>8} {r['shipped_share'] * 100:>7.1f}% "
              f"{r['span_share'] * 100:>7.1f}% {r['para_share'] * 100:>7.1f}%  {fires}")

    fp = [r for r in rows if r["shipped_fires"] and not r["span_fires"]]
    fn = [r for r in rows if r["span_fires"] and not r["shipped_fires"]]
    print(f"\n== {len(rows)} measurable pages  ({len(skipped)} left out, named below)")
    for k, lbl in (("shipped_share", "shipped (counter vs kept)"),
                   ("span_share", "same region (both passes)"),
                   ("para_share", "paragraph prose only")):
        vals = sorted(r[k] for r in rows if r["kept"] >= floor)
        print(f"   {lbl:<32} max {max(vals) * 100:>5.1f}%  p90 "
              f"{vals[int(len(vals) * .9)] * 100:>5.1f}%  median {statistics.median(vals) * 100:>5.1f}%")
    print(f"\n   gate fires on the honest corpus:  "
          + "   ".join(f"{k.replace('_fires', '')} {len([r for r in rows if r[k]])}"
                       for k in ("shipped_fires", "span_fires", "para_fires")))
    for r in fp:
        print(f"   FALSE POSITIVE (shipped fires, honest page): {r['url']}")
        print(f"      kept {r['kept']:,} of {r['kept_nc']:,} chrome-off chars → "
              f"really lost {r['span_lost']:,} ({r['span_share'] * 100:.1f}%), "
              f"counted as {r['shipped_share'] * 100:.1f}%")
        print(f"      everything it counted, by rule:")
        for label, chars in sorted(r["by_label"].items(), key=lambda kv: -kv[1])[:4]:
            print(f"        ↳ {chars:>7}  {label}")
    for r in fn:
        print(f"   MISSED by the same-region rule: {r['url']} "
              f"({r['span_share'] * 100:.1f}% vs shipped {r['shipped_share'] * 100:.1f}%)")
    if not fp and not fn:
        print("   the two agree on every honest page")

    if rounds:
        pages = [r for r in rows]      # reuse: fetch by url again from cache
        htmls = []
        for r in pages:
            try:
                htmls.append(_pg.cached_download(r["url"]))
            except Exception:
                pass
        print(f"\n== fuzz: {rounds} mutations that open a suppression inside the root")
        f = fuzz(htmls, rounds)
        print(f"   mutations scored:                    {f['n']}")
        print(f"   strict actually ate the article:     {f['n'] - f['both_clean']}")
        for k in CANDIDATES:
            print(f"   {k:<8} fires {f[k]['fires']:>5}   MISSED {f[k]['missed']:>4}"
                  + ("   <-- silent truncation" if f[k]["missed"] else "   (gate held)"))
        print(f"   cases only one of them catches:      {f['either_missed']}")
        print(f"   ^ the truth above is `any(candidate fires)` and `shipped` is one "
              f"of the candidates:\n"
              f"     this table grades three readings against a truth one of them "
              f"supplies. tests/probe_counts.py\n"
              f"     names the mutations it calls real that the page says were "
              f"never touched.")

    print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<12} {why:<40} {url}")


if __name__ == "__main__":
    main()
