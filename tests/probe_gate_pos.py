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

Eleventh awakening — the door the paragraph counter leaves closed. The tenth
measured `ptext` as the only candidate with zero false positives and zero no-cost
relaxations, and it loses 2 of 20 real truncations. The thread recorded a guess
for those two: articles that *are lists* (PEP 8, docs.python.org), text living in
`<li>` where a paragraph counter cannot see it. So this probe now attributes the
suppressed text in the root **by the kind of element that held it** (`p`, `li`,
`pre`, `td`, `other`) and adds

    plist   prose + list-item text, same reading as `ptext` and by the same
            structural rule

and — because a guess about *two cases* is not a measurement — it names them: the
kind breakdown of every real truncation, and of the ones each candidate misses. A
candidate that recovers the two by opening the `<li>` door also opens it for every
chrome list on the honest corpus, and Torrebaja's navbox (`role=navigation`) is a
list of municipality names. Whether that door is worth opening is exactly what the
breakdown decides, and the honest answer is allowed to be "no".

**Measured, and it is no.** On 62 honest pages + the same 1500 mutations:

    shipped   caught 20/20   no-cost 34
    ptext     caught 18/20   no-cost  0
    plist     caught 19/20   no-cost 24
    open      caught 14/20

`plist` fires on the honest corpus exactly once — Torrebaja — and the text it
counts there is the navbox (`li:2 999`, `td:1 233`, `p:0`): opening the `<li>` door
opens it for the chrome list this thread exists to stop counting. And the two
`ptext` misses are not the cases the guess named. One is a mutation of Torrebaja
itself, recovered only by counting the navbox that the honest page was already
dropping; the other's eaten text is `other:1 818` — neither `<p>` nor `<li>`. Of
the 20 real truncations, 19 dropped paragraph text, 8 dropped list items, so the
blind spot was never "lists": a class counter cannot be measured into existence by
the two cases it was invented for, and naming the cases is what killed the guess.

The tenth awakening's conclusion survives the eleventh: no candidate is a strict
improvement, `ptext`/`ppara` remain the only readings with zero false positives,
and the gate that ships is still the shipped one.

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

CANDIDATES = ("shipped", "span", "ptext", "open", "ppara", "plist")

# Which kind of element held the text suppression removed. Only containers that
# plausibly carry article text; everything else (a bare link label, a `<div>`
# wrapper, a `<span>`) is "other" and is deliberately *not* a candidate — the
# point of the breakdown is to see what the loss is made of before choosing.
_KIND_OF = {"p": "p", "li": "li", "pre": "pre", "code": "pre",
            "td": "td", "th": "td"}
KINDS = ("p", "li", "pre", "td", "other")


def _load_sibling(name: str):
    path = os.path.join(HERE, "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pg = _load_sibling("probe_gate")
_pr = _load_sibling("probe_rules")


def _fmt_kinds(kinds) -> str:
    """The breakdown in one cell, biggest first, empty kinds left out."""
    if not kinds:
        return "-"
    return " ".join(f"{k}:{v}" for k, v in
                    sorted(kinds.items(), key=lambda kv: -kv[1]) if v)


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
      * `sup_kind` — the same text split by the kind of element that held it
        (`p`, `li`, `pre`, `td`, `other`), so the guess "the two the prose
        counter misses are lists" can be checked against what was actually
        eaten instead of believed. `sup_ptext` keeps its own counter (and its own
        rule) so the tenth awakening's numbers stay comparable; the breakdown
        only ever counts text that is *not* inside a suppressed `<p>`, so the
        two never double-count the same characters.
    """

    def __init__(self, scope: bool = True):
        super().__init__(scope)
        self.sup_ptext = 0
        self.sup_kind: dict[str, int] = {}
        self.frames: list[dict] = []
        self._sup_p = 0          # <p> open, in the suppressed subtree
        self._marks: list[str] = []   # kinds open, in the suppressed subtree

    def handle_starttag(self, tag, attrs):
        a = self._attrs(attrs)
        tag = tag.lower()
        was = self._suppress_why()
        in_root = self._in_root_region()
        super().handle_starttag(tag, attrs)
        chrome = self._suppress_why() == "chrome"
        if not was and in_root and chrome:
            self.frames.append({
                "label": self._attr_label(tag, a), "tag": tag,
                "depth": len(self._stack), "chars": 0, "kinds": {}, "how": None,
            })
        if tag == "p" and chrome:
            self._sup_p += 1
        if tag in _KIND_OF and chrome:
            self._marks.append(_KIND_OF[tag])

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
        if suppressed_here and tag in _KIND_OF:
            kind = _KIND_OF[tag]
            for i in range(len(self._marks) - 1, -1, -1):
                if self._marks[i] == kind:
                    del self._marks[i]
                    break

    def handle_data(self, data):
        if data.strip() and self._suppress_why() == "chrome" and self._in_root_region():
            if self._sup_p:
                self.sup_ptext += len(data)
                kind = "p"
            else:
                kind = self._marks[-1] if self._marks else "other"
                self.sup_kind[kind] = self.sup_kind.get(kind, 0) + len(data)
            for f in reversed(self.frames):
                if f["how"] is None:
                    f["chars"] += len(data)
                    f["kinds"][kind] = f["kinds"].get(kind, 0) + len(data)
                    break
        super().handle_data(data)

    def kinds(self) -> dict:
        """Every character removed from the root, by kind — `p` included."""
        out = dict(self.sup_kind)
        if self.sup_ptext:
            out["p"] = out.get("p", 0) + self.sup_ptext
        return out

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
    li = pos.sup_kind.get("li", 0)
    plist = ptext + li
    open_ = sum(f["chars"] for f in pos.frames if f["how"] != "matched")
    return {
        "kept": kept,
        "kept_nc": kept_nc,
        "kept_para": pos._para,
        "sup_in_root": m["drop_in_root"],
        "sup_ptext": ptext,
        "sup_li": li,
        "sup_plist": plist,
        "sup_kind": pos.kinds(),
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
        # The eleventh awakening's door: the same reading as `ptext`, with list
        # items counted too. It is the candidate the "the two it misses are
        # lists" guess implies, and the breakdown above says whether the guess
        # is even about the right cases.
        "plist_fires": plist > kept and plist > floor,
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

    Every real truncation is also recorded with the kind breakdown of what the
    mutation removed, and every candidate's misses are named with theirs — so
    "ptext misses two, and they are lists" is either visible in the output or
    not true.
    """
    rnd = random.Random(seed)
    out = {k: {"caught": 0, "missed_real": 0, "silent_caught": 0,
               "zero_cost": 0, "partial": 0, "examples": []} for k in CANDIDATES}
    out.update({"real": 0, "silent": 0, "caught_now": 0, "n": 0,
                "real_kinds": {}})
    for _ in range(rounds):
        i = rnd.randrange(len(pages))
        src, label = pages[i]
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
            for k, v in c["sup_kind"].items():
                out["real_kinds"][k] = out["real_kinds"].get(k, 0) + 1
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
                if len(out[k]["examples"]) < 6:
                    out[k]["examples"].append({
                        "label": label, "clean": clean, "kept": c["kept"],
                        "lost": lost, "kinds": dict(c["sup_kind"]),
                        "ptext": c["sup_ptext"], "li": c["sup_li"],
                    })
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
          f"{'in_li':>7} {'unclosed':>8} {'shipped':>8} {'region':>8}  fires")
    print("-" * 104)
    for r in rows:
        fires = (("S" if r["shipped_fires"] else "-") + ("R" if r["span_fires"] else "-")
                 + ("P" if r["ptext_fires"] else "-") + ("O" if r["open_fires"] else "-"))
        print(f"{r['src']:<12} {r['kept']:>7} {r['kept_nc']:>7} {r['sup_in_root']:>8} "
              f"{r['sup_ptext']:>8} {r['sup_li']:>7} {r['sup_open']:>8} "
              f"{r['shipped_share'] * 100:>7.1f}% {r['span_share'] * 100:>7.1f}%  {fires}")

    print(f"\n== {len(rows)} measurable pages  ({len(skipped)} left out, named below)")
    print(f"   what the removed root text is made of, worst ten pages:")
    for r in rows[:10]:
        print(f"     {r['src']:<12} in_root {r['sup_in_root']:>7}  "
              f"{_fmt_kinds(r['sup_kind'])}")
    for k, lbl in (("shipped_share", "shipped (counter vs kept)"),
                   ("span_share", "same region (both passes)")):
        vals = sorted(r[k] for r in rows if r["kept"] >= floor)
        print(f"   {lbl:<32} max {max(vals) * 100:>5.1f}%  p90 "
              f"{vals[int(len(vals) * .9)] * 100:>5.1f}%  median {statistics.median(vals) * 100:>5.1f}%")
    print(f"\n   fires on the honest corpus:  "
          + "   ".join(f"{k.replace('_fires', '')} {len([r for r in rows if r[k]])}"
                       for k in ("shipped_fires", "span_fires", "ptext_fires",
                                 "ppara_fires", "plist_fires", "open_fires")))
    for k in ("shipped_fires", "span_fires", "ptext_fires", "ppara_fires",
              "plist_fires", "open_fires"):
        for r in [r for r in rows if r[k]]:
            print(f"   {k.replace('_fires', ''):<8} fires: {r['url']}  "
                  f"kept {r['kept']:,}  in_root {r['sup_in_root']:,}  "
                  f"in_ptext {r['sup_ptext']:,}  in_li {r['sup_li']:,}  "
                  f"unclosed {r['sup_open']:,}")
            print(f"       ↳ was: {_fmt_kinds(r['sup_kind'])}")
            for f in sorted(r["frames"], key=lambda f: -f["chars"])[:3]:
                print(f"       ↳ {f['chars']:>7}  {f['label']:<28} ended {f['how']}"
                      f"   {_fmt_kinds(f['kinds'])}")

    if rounds:
        # (html, label) — the page, not its name. Feeding the fuzz the label put
        # every mutation into ten characters of corpus name and reported a clean
        # zero with nothing lost: the instrument measuring the wrong object looks
        # exactly like the instrument measuring the right one.
        pages, clean_kept = [], []
        for r in rows:
            try:
                html = _pg.cached_download(r["url"])
            except Exception:
                continue
            pages.append((html, r["src"]))
            clean_kept.append(candidates(html)["kept"])
        print(f"\n== fuzz: {rounds} mutations that open a suppression inside the root")
        f = fuzz(pages, clean_kept, rounds)
        print(f"   mutations scored:                     {f['n']}")
        print(f"   the mutation really ate the article:  {f['real']}"
              f"   (strict kept > {keyhole.EMPTY_TEXT} chars and lost > half of")
        print(f"     {'':<34}the page's own clean extraction)")
        print(f"     of those, what was eaten, by kind (chars): {_fmt_kinds(f['real_kinds'])}")
        print(f"   of those, the ladder caught it:       {f['caught_now']}")
        print(f"   of those, SILENT (parse=strict):      {f['silent']}   <-- what the gate")
        print(f"     {'':<34}exists to catch")
        print(f"\n   {'':<8} {'caught':>7} {'missed':>7} {'silent':>8} {'no-cost':>8} {'partial':>8}")
        for k in CANDIDATES:
            print(f"   {k:<8} {f[k]['caught']:>7} {f[k]['missed_real']:>7} "
                  f"{f[k]['silent_caught']:>3}/{f['silent']:<4} {f[k]['zero_cost']:>8} "
                  f"{f[k]['partial']:>8}")
        for k in ("ptext", "plist"):
            for ex in f[k]["examples"]:
                print(f"   {k} MISSED: {ex['label']}  clean {ex['clean']:,} kept "
                      f"{ex['kept']:,} (lost {ex['lost']:,})  ptext {ex['ptext']:,} "
                      f"li {ex['li']:,}  eaten: {_fmt_kinds(ex['kinds'])}")

    print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<12} {why:<40} {url}")


if __name__ == "__main__":
    main()
