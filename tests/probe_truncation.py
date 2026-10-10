#!/usr/bin/env python
"""Measure whether chrome suppression can eat *part* of an article and say nothing.

The ladder was honest about one failure: a page whose strict pass keeps
*nothing*. It relaxes, and the relaxed pass names itself (`parse=no-chrome`).

This probe measured the other half of that — suppression eating *most* of the
article while leaving enough to pass `_has_content`. Then no rung fired,
`parse=strict` printed, and the page read as a short one: the silent truncation,
the empty success wearing the costume of a page that simply had little text.

Measuring it needs a discriminator, because suppression removing text is not
itself a bug: nav, sidebars and footers *should* go. The one that isn't fine is
suppression removing readable text **inside the content root**, which is where
the article lives. So this probe instruments a _Reader to count, per rule and
per label, the readable characters dropped while the root frame was open:

    drop_in_root   chars of article-region text suppression removed
    kept           chars the strict result actually returned

`drop_in_root / (kept + drop_in_root)` is the share of the root's readable text
that suppression threw away — the same quantity the shipped gate now reads
(`keyhole.root_lost_share`), computed from the shipped reader, not from a model
of it. On a clean page it stays small (Wikipedia's Vector skin keeps a language
switcher and a table of contents inside `<main>` — chrome that legitimately
lives in the root; npm's readme keeps its sidebars). When the strict pass threw
away more than it kept, the ladder now relaxes and names the number
(`parse=trunc-root:NN%`) instead of shipping the stub.

So this probe is both the record of why the gate sits at 50% and the check that
it still fires only where it should:

  * clean pages: ratio vs the gate, with the margin (a clean page at the gate
    would mean the gate is eating honest pages)
  * fuzz, rescued/clean/missed — `missed > 0` means a silent truncation got past
    the gate, which is the one result that fails this probe

Run:  python tests/probe_truncation.py [--fuzz N]
"""
import importlib.util
import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402
from keyhole import _NoChromeReader, _Reader  # noqa: E402


def _load_sibling(name: str):
    """Load a sibling probe by path so nothing is duplicated between them.

    `chrome_rule` lives in probe_rules.py and is *the* naming mirror of the
    shipped predicate (test_keyhole asserts the two agree). Re-importing it here
    means this probe cannot drift from that one, and the sites and the download
    helper come from there too: the instrument is shared, not re-typed.
    """
    path = os.path.join(HERE, "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pr = _load_sibling("probe_rules")
chrome_rule = _pr.chrome_rule
SITES = _pr.SITES

CACHE = os.path.join(tempfile.gettempdir(), "keyhole_trunc_cache")


def cached_download(url: str) -> str:
    """`probe_rules.download`, memoised on disk so a re-run and a fuzz round sees
    the same bytes (a page that changes between two measurements is the
    instrument disagreeing with itself)."""
    os.makedirs(CACHE, exist_ok=True)
    key = "".join(c if c.isalnum() else "_" for c in url)[:120]
    path = os.path.join(CACHE, key + ".html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    html = _pr.download(url)
    with open(path, "w", encoding="utf-8", errors="replace", newline="\n") as fh:
        fh.write(html)
    return html


class _Trunc(_Reader):
    """A _Reader that attributes the readable characters chrome suppression
    removes inside the root region to the rule that matched.

    It does not reimplement "inside the root": it calls the shipped
    `_in_root_region()`, so the instrument cannot disagree with the gate about
    where the article is — which is exactly how the density probe once predicted
    a number keyhole did not produce.
    """

    def __init__(self, scope: bool = True):
        super().__init__(scope)
        self.drop_in_root = 0
        self.drop_out_root = 0
        self.by_label: dict[str, int] = {}
        self._arec: list = []   # parallel to _stack: [rule, label, chars] or None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = self._attrs(attrs)
        rule = chrome_rule(tag, a)
        was_sup = self._suppressed()
        if tag not in keyhole._VOID_TAGS:
            if not was_sup and rule:
                self._arec.append([rule, f"{rule} @ {_Reader._attr_label(tag, a)}", 0])
            elif was_sup:
                self._arec.append(next((e for e in reversed(self._arec) if e is not None), None))
            else:
                self._arec.append(None)
        super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
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
                rec[2] += len(data)
                if self._in_root_region():
                    self.by_label[rec[1]] = self.by_label.get(rec[1], 0) + len(data)
                else:
                    self.drop_out_root += len(data)
        super().handle_data(data)


def nochrome_text_len(html: str) -> int:
    return len(keyhole._text_of(keyhole._reader(html, _NoChromeReader)))


def measure(html: str) -> dict:
    """One page, measured four ways: what suppression cost, what the strict pass
    kept, what the shipped ladder did about it, and what the caller got."""
    p = keyhole._reader(html, _Trunc)
    real = keyhole.analyze(html)
    kept = len(keyhole._text_of(p))
    shipped = len(keyhole._text_of(real))
    return {
        "kept": kept,                       # strict pass, had it been trusted
        "shipped": shipped,                 # what analyze() actually returned
        "drop_in_root": p.sup_in_root,
        "drop_out_root": p.drop_out_root,
        "ratio": keyhole.root_lost_share(p),
        "ate": keyhole.ate_the_root(p),     # the shipped gate, asked of the
                                            # shipped reader rather than a model
        "scope": p.scope,
        "rung": real.rung,
        "by_label": dict(p.by_label),
    }


def top(labels: dict, n: int = 3) -> list:
    return sorted(labels.items(), key=lambda kv: -kv[1])[:n]


def fuzz(pages, rounds, seed=0):
    """Mutate real pages so a suppression opens *inside* the root and never
    closes — the shape that eats the article's tail — and count what the ladder
    does about it.

    Four populations:

      empty    strict kept nothing, so the ladder relaxed and said so
      trunc    strict kept a minority of the root, so the ladder relaxed, named
               the share, and shipped the page instead of the stub
      clean    the strict pass was right
      missed   strict shipped a minority of the root and said nothing — the
               silent truncation this probe exists to catch; must be 0

    plus `below`, the cases where suppression did drop more than the result kept
    but the loss was smaller than an empty page (``keyhole.EMPTY_TEXT``): left
    strict on purpose, and reported so the floor's price is visible rather than
    assumed to be free.
    """
    rnd = random.Random(seed)
    empty = trunc = clean = missed = below = 0
    below_max = 0
    ratios: list[float] = []
    recovered = 0
    worst = []
    for _ in range(rounds):
        src = rnd.choice(pages)
        # Where to open the suppressions: inside the root when the page has one,
        # because a suppression outside it is chrome doing its job.
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
        m = measure(html)
        if m["rung"] == "strict":
            if m["ate"]:
                missed += 1            # the gate had the case and did not fire
                worst.append(m)
            elif m["drop_in_root"] > m["kept"]:
                below += 1             # a real loss, under the floor: on purpose
                below_max = max(below_max, m["drop_in_root"])
            else:
                clean += 1
        elif m["rung"] == "no-chrome":
            empty += 1
        else:
            trunc += 1
            ratios.append(m["ratio"])
            recovered += m["shipped"] - m["kept"]
            worst.append(m)
    worst.sort(key=lambda m: -m["drop_in_root"])
    return empty, trunc, clean, missed, below, below_max, ratios, recovered, worst


def main():
    rounds = 0
    if "--fuzz" in sys.argv:
        i = sys.argv.index("--fuzz")
        rounds = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 3000
    gate = keyhole.ATE_ROOT
    print(f"keyhole {keyhole.__version__} — can suppression eat part of the article silently?\n")
    pages = []
    print(f"{'site':<10} {'kept':>7} {'shipped':>8} {'in_root':>8} {'out_root':>8} "
          f"{'ratio':>7} {'margin':>7}  rung")
    base_ratios = []
    for name, url in SITES:
        try:
            html = cached_download(url)
        except Exception as e:
            print(f"{name:<10} FETCH FAILED: {type(e).__name__}: {e}")
            continue
        pages.append(html)
        m = measure(html)
        base_ratios.append(m["ratio"])
        print(f"{name:<10} {m['kept']:>7} {m['shipped']:>8} {m['drop_in_root']:>8} "
              f"{m['drop_out_root']:>8} {m['ratio'] * 100:>6.1f}% "
              f"{(gate - m['ratio']) * 100:>6.1f}%  {m['rung']}")
        for label, chars in top(m["by_label"]):
            print(f"           ↳ {chars:>7}  {label}")
    if base_ratios:
        worst = max(base_ratios)
        print(f"\nclean-page ratio: max {worst * 100:.1f}%  "
              f"mean {sum(base_ratios) / len(base_ratios) * 100:.1f}%  "
              f"gate {gate * 100:.0f}%  margin {(gate - worst) * 100:.1f} points")
        tripped = [n for (n, _), r in zip(SITES, base_ratios) if r > gate]
        print(f"clean pages the gate would eat: {tripped or 'none'}")
    if rounds and pages:
        (empty, trunc, clean, missed, below, below_max,
         ratios, recovered, worst) = fuzz(pages, rounds)
        print(f"\n== fuzz: {rounds} mutations that open a suppression inside the root ==")
        print(f"  clean (strict was right):            {clean}")
        print(f"  rescued from nothing (no-chrome):    {empty}")
        print(f"  rescued from a stub (trunc-root):    {trunc}")
        print(f"  held back by the floor:              {below}"
              + (f" (biggest loss {below_max} chars)" if below else ""))
        print(f"  MISSED (shipped a stub silently):    {missed}"
              + ("  <-- the gate failed" if missed else "  (gate held)"))
        if ratios:
            recovered_per = recovered / len(ratios)
            print(f"  trunc-root ratio: min {min(ratios) * 100:.1f}%  "
                  f"median {sorted(ratios)[len(ratios) // 2] * 100:.1f}%  "
                  f"max {max(ratios) * 100:.1f}%")
            print(f"  text the gate recovered: {recovered:,} chars "
                  f"({recovered_per:,.0f} per page it fired on)")
        for m in worst[:3]:
            print(f"\n  worst: kept={m['kept']} shipped={m['shipped']} "
                  f"in_root={m['drop_in_root']} ({m['ratio'] * 100:.0f}% of the root) "
                  f"rung={m['rung']} scope={m['scope'] or 'none'}")
            for label, chars in top(m["by_label"]):
                print(f"         ↳ {chars:>7}  {label}")


if __name__ == "__main__":
    main()
