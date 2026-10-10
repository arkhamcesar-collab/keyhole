#!/usr/bin/env python
"""Where does the loss fall? A positional counter for the trunc-root gate.

The ninth awakening fed the gate a corpus nobody curated (`probe_gate.py`) and it
relaxed on an honest, complete page: `en.wikipedia.org/wiki/Torrebaja`,
`trunc-root:62%`. The article was whole — it ends in References and the stub note
— but suppression had removed 3,173 characters from the same container the result
came from, because Vector 2022 keeps the municipality navbox, the authority-control
block and the categories *inside* `div.mw-content-ltr`.

Two counters were tried and both are dead ends, and the honest reading is that the
*quantity* is wrong, not the threshold:

  shipped   (counter vs kept)     1 false positive on 62 honest pages, 0 of 21 misses
  span      (both passes)         2 of 21 misses — fixes Zacatecas, not Torrebaja
  para      (prose only)          0 false positives, **17 of 21 misses**

`para` is the interesting failure, because the idea was right and the instrument
was broken. `_ParaLoss` counted text suppressed while `self._para_depth` was up —
but `_para_depth` is incremented only for a `<p>` that is *not* suppressed, and a
`<p>` opened inside a suppressed subtree never increments it. So under mutation,
where the injected `<aside>` swallows the article's own paragraphs, the counter
reads ~0: it is blind to exactly the prose it was built to see, and it reports a
clean zero that looks like a clean corpus. That is the instrument lying again,
this time by parity with its own blind spot.

So this probe asks the question in the shape the thread left: **is the loss at the
end of the container, or is it the article's continuation?** Two structural
readings, both measured against the same corpora (the uncurated honest list plus
the destructive fuzz that calibrated the gate):

    ptext   readable text suppression removed from inside a `<p>` *anywhere* in
            the suppressed subtree — the paragraph attribution done structurally,
            without asking `_para_depth` (which cannot see in there)
    open    text removed by a chrome frame that never matched its own end tag —
            a suppression that closed by unwind, or was still open when the root
            closed. That is the shape of the tail-eating aside: it was opened
            inside the article and never closed.

Both keep the gate's floor (`keyhole.EMPTY_TEXT`): a share on a stub decides
nothing. And both are scored on the same two numbers that decide everything —
false positives on honest pages, misses under mutation — because a narrower gate
pays for every honest page it saves with a silent truncation it stops catching.

Run:  python tests/probe_gate_pos.py [--fuzz N] [--min-chars N]
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

CANDIDATES = ("shipped", "span", "ptext", "open", "ppara")


def _load_sibling(name: str):
    path = os.path.join(HERE, "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pg = _load_sibling("probe_gate")
_pr = _load_sibling("probe_rules")


class _PosReader(_Reader):
    """Attribute chrome suppression inside the root to *where* it came from.

    It does not reimplement "inside the root": it calls the shipped
    `_in_root_region()` (as probe_truncation does), so the instrument cannot
    disagree with the gate about where the article is. What it adds is structure:

      * per-frame accounting — which element opened the suppression, how much
        readable text it removed, and how it ended (`matched` by its own end tag,
        `unwind` by an enclosing tag's, or `open` still on the stack at the end);
      * `sup_ptext` — readable text removed from inside a `<p>` *in the
        suppressed subtree*, counted by structure and not by `_para_depth`
        (`_ParaLoss`'s blind spot: a `<p>` opened inside suppression never
        increments it, so the prose counter read 0 on the exact cases it was
        written for).
    """

    def __init__(self, scope: bool = True):
        super().__init__(scope)
        self.sup_ptext = 0
        self.frames: list[dict] = []
        self._sup_p = 0          # <p> open, in the suppressed subtree

    def handle_starttag(self, tag, attrs):
        a = self._attrs(attrs)
        tag = tag.lower()
        was = self._suppress_why()
        in_root = self._in_root_region()
        super().handle_starttag(tag, attrs)
        if not was and in_root and self._suppress_why() == "chrome":
            self.frames.append({
                "label": self._attr_label(tag, a), "tag": tag,
                "depth": len(self._stack), "chars": 0, "how": None,
            })
        if tag == "p" and self._suppress_why() == "chrome":
            self._sup_p += 1

    def handle_endtag(self, tag):
        tag = tag.lower()
        idx = None
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                idx = i
                break
        suppressed_here = self._suppress_why() == "chrome"
        super().handle_endtag(tag)
        if idx is not None:
            for f in self.frames:
                if f["how"] is not None or f["depth"] <= idx:
                    continue
                # the frame this tag closes is a match; anything deeper is unwound
                f["how"] = ("matched" if (f["depth"] == idx + 1 and f["tag"] == tag)
                            else "unwind")
        if tag == "p" and suppressed_here and self._sup_p:
            self._sup_p -= 1

    def handle_data(self, data):
        if data.strip() and self._suppress_why() == "chrome" and self._in_root_region():
            if self._sup_p:
                self.sup_ptext += len(data)
            for f in reversed(self.frames):
                if f["how"] is None:
                    f["chars"] += len(data)
                    break
        super().handle_data(data)

    def close(self):
        super().close()
        for f in self.frames:
            if f["how"] is None:
                f["how"] = "open"


def candidates(html: str) -> dict:
    """The shipped gate's numbers next to the two structural readings."""
    m = _pg.measure(html)
    kept = m["kept"]
    nc = keyhole._reader(html, _NoChromeReader)
    kept_nc = len(keyhole._text_of(nc))
    lost = max(0, kept_nc - kept)
    pos = keyhole._reader(html, _PosReader)
    floor = keyhole.EMPTY_TEXT
    ptext = pos.sup_ptext
    open_ = sum(f["chars"] for f in pos.frames if f["how"] != "matched")
    return {
        "kept": kept,
        "kept_nc": kept_nc,
        "kept_para": pos._para,
        "sup_in_root": m["drop_in_root"],
        "sup_ptext": ptext,
        "sup_open": open_,
        "shipped_share": m["ratio"],
        "shipped_fires": m["ate"],
        "span_share": (lost / kept_nc) if kept_nc else 0.0,
        "span_fires": lost > kept and lost > floor,
        "ptext_fires": ptext > kept and ptext > floor,
        # Prose lost measured against prose kept — the one pairing where both
        # sides are the same region *and* the same kind of text. `ptext` above
        # divides the root's paragraph loss by the narrowed span's whole text,
        # which is two regions again: a suppressed <p> sitting in the root but
        # outside the tightened container was never in `kept` to be lost, and
        # counting it fires on pages nothing happened to.
        "ppara_fires": ptext > pos._para and ptext > floor,
        "open_fires": open_ > kept and open_ > floor,
        "frames": pos.frames,
        "rung": m["rung"],
        "scope": m["scope"],
        "by_label": m["by_label"],
    }


def fuzz(pages, clean_kept, rounds, seed=0):
    """The mutations that calibrated the gate, scored by every candidate.

    The one thing this probe does differently is the *grading*. Both earlier
    probes (`probe_truncation`, `probe_gate_span`) called a mutation a real
    truncation when any reading said the strict pass ate the article — and the
    shipped reading was one of them, so "shipped missed 0" was true by
    construction: the gate was grading its own exam. The cost of that is visible
    in the cases it hides. Torrebaja's honest false positive (ninth awakening)
    fires on the mutation too, keeps the same 2,752 characters it kept when
    clean, and every candidate that stays quiet on it is charged a *miss* for
    text nobody lost. The instrument was back, in its fourth costume: not the
    similar instrument, not the desynchronised one, not the one attributing the
    wrong cause — the one grading itself.

    So the truth used here is the mutation's own effect, measured against the
    page it was cut from: the strict pass ate the article when the mutated
    extraction lost more than half of the text the *clean* page's strict pass
    returned. Nothing in that definition reads a candidate, and no candidate can
    fail it by disagreeing with the gate.

    `fires_clean_quiet` is kept too, because it is the number a replacement rule
    lives or dies on: a candidate that fires where the shipped gate doesn't is
    not free, it is *adding* a relaxation, and every one of those costs an
    honest page unless it is also right.
    """
    rnd = random.Random(seed)
    out = {k: {"caught": 0, "missed_real": 0, "silent_caught": 0,
               "zero_cost": 0, "partial": 0} for k in CANDIDATES}
    out.update({"real": 0, "silent": 0, "caught_now": 0, "n": 0})
    for _ in range(rounds):
        i = rnd.randrange(len(pages))
        src = pages[i]
        clean = clean_kept[i]
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
        lost = clean - c["kept"]
        # The article was really eaten only if the strict pass still returned
        # something a caller could read — otherwise the *first* rung already
        # fired and there is no silence to catch (a mutation that leaves six
        # characters is a destroyed page, not a truncated one).
        real = lost > clean * 0.5 and lost > keyhole.EMPTY_TEXT and c["kept"] > keyhole.EMPTY_TEXT
        silent = real and c["rung"] == "strict"
        if real:
            out["real"] += 1
            if silent:
                out["silent"] += 1
            else:
                out["caught_now"] += 1
        for k in CANDIDATES:
            if c[f"{k}_fires"]:
                if real:
                    out[k]["caught"] += 1
                    if silent:
                        out[k]["silent_caught"] += 1
                elif lost > 0:
                    # the page lost real text, just not half of it: relaxing
                    # here gives that text back (with the chrome). Not a loss.
                    out[k]["partial"] += 1
                else:
                    # nothing was lost and the rule relaxed anyway: this is the
                    # Torrebaja shape — the expensive one, because it re-adds
                    # chrome to a page that was complete and labels it truncated.
                    out[k]["zero_cost"] += 1
            elif real:
                out[k]["missed_real"] += 1
    return out


def main():
    rounds = 0
    if "--fuzz" in sys.argv:
        i = sys.argv.index("--fuzz")
        rounds = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 1500
    args = [a for a in sys.argv[1:] if not a.startswith("--") and not a.isdigit()]
    path = args[0] if args else DEFAULT_LIST
    floor = keyhole.EMPTY_TEXT
    if "--min-chars" in sys.argv:
        floor = int(sys.argv[sys.argv.index("--min-chars") + 1])

    urls = _pg.read_list(path) + [(f"old-{n}", u) for n, u in
                                  [(s.replace(".", ""), u) for s, u in _pr.SITES]]
    print(f"keyhole {keyhole.__version__} — where does the loss fall?\n"
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
    print(f"{'src':<12} {'kept':>7} {'kc':>7} {'in_root':>8} {'in_ptext':>8} "
          f"{'unclosed':>8} {'shipped':>8} {'region':>8}  fires")
    print("-" * 96)
    for r in rows:
        fires = (("S" if r["shipped_fires"] else "-") + ("R" if r["span_fires"] else "-")
                 + ("P" if r["ptext_fires"] else "-") + ("O" if r["open_fires"] else "-"))
        print(f"{r['src']:<12} {r['kept']:>7} {r['kept_nc']:>7} {r['sup_in_root']:>8} "
              f"{r['sup_ptext']:>8} {r['sup_open']:>8} {r['shipped_share'] * 100:>7.1f}% "
              f"{r['span_share'] * 100:>7.1f}%  {fires}")

    print(f"\n== {len(rows)} measurable pages  ({len(skipped)} left out, named below)")
    for k, lbl in (("shipped_share", "shipped (counter vs kept)"),
                   ("span_share", "same region (both passes)")):
        vals = sorted(r[k] for r in rows if r["kept"] >= floor)
        print(f"   {lbl:<32} max {max(vals) * 100:>5.1f}%  p90 "
              f"{vals[int(len(vals) * .9)] * 100:>5.1f}%  median {statistics.median(vals) * 100:>5.1f}%")
    print(f"\n   fires on the honest corpus:  "
          + "   ".join(f"{k.replace('_fires', '')} {len([r for r in rows if r[k]])}"
                       for k in ("shipped_fires", "span_fires", "ptext_fires",
                                 "ppara_fires", "open_fires")))
    for k in ("shipped_fires", "span_fires", "ptext_fires", "ppara_fires", "open_fires"):
        for r in [r for r in rows if r[k]]:
            print(f"   {k.replace('_fires', ''):<8} fires: {r['url']}  "
                  f"kept {r['kept']:,}  in_root {r['sup_in_root']:,}  "
                  f"in_ptext {r['sup_ptext']:,}  unclosed {r['sup_open']:,}")
            for f in sorted(r["frames"], key=lambda f: -f["chars"])[:3]:
                print(f"       ↳ {f['chars']:>7}  {f['label']:<28} ended {f['how']}")

    if rounds:
        htmls = []
        for r in rows:
            try:
                htmls.append(_pg.cached_download(r["url"]))
            except Exception:
                pass
        clean_kept = [candidates(h)["kept"] for h in htmls]
        print(f"\n== fuzz: {rounds} mutations that open a suppression inside the root")
        f = fuzz(htmls, clean_kept, rounds)
        print(f"   mutations scored:                     {f['n']}")
        print(f"   the mutation really ate the article:  {f['real']}"
              f"   (strict kept > {keyhole.EMPTY_TEXT} chars and lost > half of")
        print(f"     {'':<34}the page's own clean extraction)")
        print(f"   of those, the ladder caught it:       {f['caught_now']}")
        print(f"   of those, SILENT (parse=strict):      {f['silent']}   <-- what the gate")
        print(f"     {'':<34}exists to catch")
        print(f"\n   {'':<8} {'caught':>7} {'missed':>7} {'silent':>8} {'no-cost':>8} {'partial':>8}")
        for k in CANDIDATES:
            print(f"   {k:<8} {f[k]['caught']:>7} {f[k]['missed_real']:>7} "
                  f"{f[k]['silent_caught']:>3}/{f['silent']:<4} {f[k]['zero_cost']:>8} "
                  f"{f[k]['partial']:>8}")

    print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<12} {why:<40} {url}")


if __name__ == "__main__":
    main()
