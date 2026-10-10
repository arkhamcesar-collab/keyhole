#!/usr/bin/env python
"""The gate fires 43 times on an honest corpus. What is that text made of?

The twenty-eighth awakening measured the census on a corpus ten times larger and
found the shipped gate relaxing on **43 of 353 honest pages — 12%, every one of
them Wikipedia** — while on the front-page sources it fires 0 of 37. The ninth
awakening had already said what a fire on a complete page looks like:
``Torrebaja``, article whole, ``trunc-root:62%``, and the share came from
counting the municipality navbox, the authority-control block and the categories
that Vector 2022 keeps *inside* ``div.mw-content-ltr``. One page was enough to
call that a false positive. Forty-three pages are not one page, and "the gate is
wrong on 12% of Wikipedia" is a stronger claim than the ninth made:

    is that 12% the ninth's shape — chrome a reader never sees, ``p:0`` — or a
    legitimate rescue, the gate catching prose that really was eaten?

The answer is a census, and this side needs no mutation to read it: these fires
are all on pages nothing happened to. It is read four ways, and the fourth is not
a kind at all — because a count of *something else* cannot be the only witness
that nothing was lost:

* **by kind.** ``_PosReader`` (the eleventh awakening's instrument) attributes
  every suppressed character *not* inside a suppressed ``<p>`` to the kind of
  element that held it (``li``, ``pre``, ``td``, ``other``) and counts the rest
  as ``p``. A navbox is a list of names, authority control is a table, the
  categories are a ``<ul>``: if the fires are the ninth's shape, their eaten text
  is ``p:0`` and the article's own paragraphs were never touched.
* **by links.** Chrome is link-dense and prose is not, and no kind counter can
  see that — a ``<li>`` in a navbox and a ``<li>`` in a recipe are the same kind.
  This probe adds exactly one counter to the sibling's reader (``sup_link``): how
  many of the removed characters were a link's own label. It is a second reading
  of "this is chrome", and two readings of one fact are allowed to disagree.
* **by how the frame ended.** The fourteenth and twenty-second awakenings built
  the frame ledger — ``matched`` by its own end tag, ``unwind`` by an enclosing
  one, ``open`` still on the stack at the end — and the damage this gate exists
  to catch has a shape: the tail-eating aside is a frame that never closed. A
  navbox is a frame that opened and matched. So the same census split by ``how``
  separates "the gate relaxed on a closed chrome block" from "the gate relaxed
  on a suppression that was eating the article".
* **by the paragraph delta.** ``kept_para`` is text inside a ``<p>`` that
  suppression did not touch; the same quantity on the ``_NoChromeReader`` pass is
  page-wide paragraph text with no chrome removed. The delta between them is
  paragraph text that chrome removal cost, attributed by nothing — so a fire with
  a zero delta lost no prose anywhere, whatever the kinds say, and a fire with a
  positive delta is prose loss the kind census has to account for.

**Measured, and the 12% is the ninth awakening's shape, forty-three times over.**
On the twenty-eighth awakening's sample (353 pages, digest ``e8d5df572463cd5c`` —
``--extended`` reproduces that digest exactly, and *without* it the same corpus is
348 pages: five of them have no root at all, so the plain guard drops them, which
is the twenty-sixth awakening's finding still standing. Two samples, two digests,
and the run says which one it measured) the shipped gate relaxes on **43 pages and
eats 208,626 characters** doing it:

    by kind                  li 182,919   td 18,505   other 7,124   p 78
    by links                 172,028 of 208,626 are a link's own label  (82.5%)
    by how the frame ended   matched 208,626   unwind 0   open 0

Three readings, not one mutation:

* **41 of the 43 fires ate no prose at all** — ``sup_ptext`` 0 *and* the page-wide
  paragraph delta 0, two counters that share no code path, and they disagree on
  **0** pages.
* The **two fires that did** ate **78 characters** between them, 0.04% of the
  total, and they ate them inside containers the chrome rule already calls chrome
  for structural reasons: ``table.sidebar`` on
  *1864 New York gubernatorial election* (``p:74`` — an infobox, and a `<p>` in a
  sidebar table is a caption) and the navbox ``div#mwAh4`` on *Volker Kauder*
  (``p:4``).
* **No fire has an unmatched frame**: all 208,626 characters were removed by
  chrome frames that closed with their own end tag. The shape this gate exists to
  catch — the tail-eating aside, the suppression that unwinds or is still open
  when the root closes — is **absent from the honest side entirely**.

So the twenty-eighth awakening's own headline ("the shipped gate relaxes on 43 of
353 honest pages — 12%, every one of them Wikipedia") reads as the gate being
wrong, and the census corrects it in the direction that is measurable: the 12% is
**chrome Vector 2022 keeps inside the content root** — the navbox, the
authority-control table, the categories — and a reader never saw a character of
it. `li` is 87.7% of what was eaten and link labels are 82.5%: that is a navbox,
and the ninth awakening's one page was the first of forty-three.

**The honest side of the price, at 353 pages instead of 62** — this half, with no
mutations, is what a replacement rule is judged by first:

    shipped   43 of 353 fires       plist   31        ptext    0
    span      26 of 353             ppara    0        punion   0        open 0

The eleventh awakening closed the ``<li>`` door on 62 pages, and at 353 pages it
is still open 31 times; the prose readings fire **not once**, and neither do the
frames that never closed. That last line is the census's own arithmetic — on this
sample the honest fires and the damage are disjoint sets in the frame ledger — but
it is *half* a price: the captures are mutations, and mutations are not in this
file. The 353 pages have never been fuzzed (the twenty-eighth awakening's open
item 2), so every capture number the family quotes belongs to the family's sample
and is attributed to it.

Run:  python tests/probe_fires.py [--list PATH] [--order=url] [--extended]

The sample defaults to ``tests/corpus/band_urls.txt``, the 353 pages whose census
the twenty-eighth awakening measured, and ``pin_order`` prints its digest: either
this run's pages are that sample or the run says it is another one. The census is
order-invariant, so ``--order=url`` changes the digest's meaning and not the
numbers.

Named rather than implied: the *other* half of the price, the fuzz, is not run
here (the twenty-eighth awakening's open item 2). This probe is the honest side
only. What it can decide is whether the 12% has the ninth's shape; what a
prose-gated replacement would stop catching is a question about mutations and is
not answered by a census of pages nothing happened to.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402
from keyhole import _NoChromeReader  # noqa: E402

DEFAULT_LIST = os.path.join(HERE, "tests", "corpus", "band_urls.txt")


def _load_sibling(name: str):
    path = os.path.join(HERE, "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_gpos = _load_sibling("probe_gate_pos")
_pg = _load_sibling("probe_gate")


class _FireReader(_gpos._PosReader):
    """The sibling's reader, plus one counter: link labels among the eaten text.

    Chrome is link-dense and prose is not, and none of the kind counters can see
    that — ``li`` is ``li`` in a navbox, in a bibliography and in a recipe. So
    this subclass tracks how deep it is in an ``<a>`` and adds the readable
    characters removed while inside one to ``sup_link``.

    Nothing else about the sibling changes: the counters, the frames, the region
    test (``_in_root_region``) and the chrome test (``_suppress_why``) are its
    own, so ``sup_kind``/``sup_ptext`` here are the same numbers the sibling
    prints and the new counter is the only difference between them.
    """

    def __init__(self, scope: bool = True):
        super().__init__(scope)
        self.sup_link = 0
        self._a_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._a_depth += 1
        super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._a_depth:
            self._a_depth -= 1
        super().handle_endtag(tag)

    def handle_data(self, data):
        if (self._a_depth and data.strip()
                and self._suppress_why() == "chrome" and self._in_root_region()):
            self.sup_link += len(data)
        super().handle_data(data)


def _sum_kinds(rows) -> dict:
    tot: dict = {}
    for r in rows:
        for k, v in r["sup_kind"].items():
            tot[k] = tot.get(k, 0) + v
    return tot


def _pct(n: int, d: int) -> str:
    return f"{(100.0 * n / d) if d else 0.0:.1f}%"


def _fire_line(r, w=12) -> str:
    return (f"   {r['src']:<{w}} kept {r['kept']:>7,}  in_root {r['sup_in_root']:>7,}  "
            f"{r['shipped_share'] * 100:>5.1f}%   "
            f"links {_pct(r['sup_link'], r['sup_in_root']):>6}   "
            f"para +{r['para_delta']:>6,}   {_gpos._fmt_kinds(r['sup_kind'])}")


def main():
    floor = keyhole.EMPTY_TEXT
    path = DEFAULT_LIST
    if "--list" in sys.argv:
        path = sys.argv[sys.argv.index("--list") + 1]
    else:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        if args:
            path = args[0]
    extended = "--extended" in sys.argv

    urls = _pg.read_list(path)
    print(f"keyhole {keyhole.__version__} — what the gate's fires are made of\n"
          f"corpus: {path}  ({len(urls)} urls)   floor {floor}"
          + ("   --extended (only the floor excludes)\n" if extended else "\n"))

    rows, skipped, desync, census_desync = [], [], [], []
    for src, url in urls:
        if not _pg.is_html(url):
            skipped.append((src, url, "not html"))
            continue
        try:
            html = _pg.cached_download(url)
        except Exception as e:
            skipped.append((src, url, f"{type(e).__name__}"[:30]))
            continue
        c = _gpos.candidates(html)
        # The band sample's own guard, unchanged, so this run's sample is that
        # awakening's sample and the digest below is the witness.
        if c["kept"] < floor or (not extended and not c["scope"]):
            skipped.append((src, url, f"no region ({c['kept']} kept, "
                                      f"scope {c['scope'] or 'none'})"))
            continue
        fire = keyhole._reader(html, _FireReader)
        # The fourth reading, and the only one that does not go through the
        # chrome attribution at all: paragraph text kept, against the same
        # quantity on the pass that removes no chrome. `_para` counts a `<p>`'s
        # own text, and only for a `<p>` suppression did not touch — so the delta
        # is prose removal with no attribution to argue about.
        para_nc = keyhole._reader(html, _NoChromeReader)._para
        # The census has to cover the gate's own numerator exactly, or this probe
        # is measuring a neighbourhood of the question: `sup_in_root` is chrome
        # suppression inside the root, and the sibling's kinds are the same text
        # sorted. A page where they differ is named, not averaged. The subclass is
        # checked the same way — a new counter that moves the old ones is the
        # instrument changing the thing it measures.
        if sum(c["sup_kind"].values()) != c["sup_in_root"]:
            census_desync.append((src, url, c["sup_in_root"],
                                  sum(c["sup_kind"].values())))
        if fire.sup_ptext + sum(fire.sup_kind.values()) != c["sup_in_root"]:
            desync.append((src, url, c["sup_in_root"],
                           fire.sup_ptext + sum(fire.sup_kind.values())))
        rows.append({"src": src, "url": url, **c, "sup_link": fire.sup_link,
                     "para_delta": max(0, para_nc - c["kept_para"])})

    digest = _gpos.pin_order(rows, sys.argv)

    # -- the fires, named, with what each one ate ---------------------------
    fires = [r for r in rows if r["shipped_fires"]]
    print(f"\n== the fires: {len(fires)} of {len(rows)} honest pages the shipped "
          f"gate relaxes on")
    for r in sorted(fires, key=lambda r: -r["shipped_share"]):
        print(_fire_line(r))
    if not fires:
        print("   none — the census has no subject on this sample")
        return

    # -- the same census over the fires -------------------------------------
    tot_in = sum(r["sup_in_root"] for r in fires)
    kinds = _sum_kinds(fires)
    links = sum(r["sup_link"] for r in fires)
    prose_free = [r for r in fires if not r["sup_ptext"]]
    para_zero = [r for r in fires if not r["para_delta"]]
    both = [r for r in fires if not r["sup_ptext"] and not r["para_delta"]]
    print(f"\n== the census over the fires: what those {len(fires)} relaxations ate")
    print(f"   eaten from the root: {tot_in:,} chars across {len(fires)} pages")
    print(f"   by kind:  {_gpos._fmt_kinds(kinds)}")
    print(f"   of that, link labels: {links:,} ({_pct(links, tot_in)})"
          f"   <-- chrome is link-dense; prose is not")
    how: dict = {}
    for r in fires:
        for f in r["frames"]:
            how[f["how"]] = how.get(f["how"], 0) + f["chars"]
    print(f"   by how the frame that ate it ended:  {_gpos._fmt_kinds(how)}"
          f"   <-- the tail-eating frame is the one that never matched")
    labels: dict = {}
    for r in fires:
        for f in r["frames"]:
            labels[f["label"]] = labels.get(f["label"], 0) + f["chars"]
    print("   top frames by chars:")
    for lab, ch in sorted(labels.items(), key=lambda kv: -kv[1])[:6]:
        n = len({r["url"] for r in fires
                 if any(f["label"] == lab for f in r["frames"])})
        print(f"     {ch:>8,}  {lab:<34} on {n} page(s)")
    print(f"\n   fires that ate no prose (kind census, sup_ptext 0): "
          f"{len(prose_free)} of {len(fires)}")
    print(f"   fires with no paragraph loss at all (page-wide delta 0): "
          f"{len(para_zero)} of {len(fires)}")
    print(f"   fires where the two readings agree there was no prose loss: "
          f"{len(both)} of {len(fires)}")
    disc = [r for r in fires if (not r["sup_ptext"]) != (not r["para_delta"])]
    print(f"   fires where they disagree: {len(disc)}"
          + ("" if not disc else "  <-- named below, one reading of the two is wrong"))
    for r in disc:
        print(f"     {r['src']:<12} in_root {r['sup_in_root']:>7,}  "
              f"sup_ptext {r['sup_ptext']:>6,}  para delta {r['para_delta']:>6,}  "
              f"{r['url']}")
    # The fires that did eat prose are the only ones with a question left in them,
    # so they are the only ones that get their frames printed: what held the
    # `<p>`, how that frame ended, and what else it ate. A prose fire whose frame
    # is a navbox is a caption or a stub line, and this is where it is named.
    for r in [x for x in fires if x["sup_ptext"]]:
        print(f"\n     {r['src']:<12} {r['sup_ptext']:>5,} prose chars — "
              f"the frames that held them:")
        for f in sorted(r["frames"], key=lambda f: -f["chars"])[:3]:
            print(f"       {f['chars']:>7,}  {f['label']:<28} ended {f['how']:<8} "
                  f"{_gpos._fmt_kinds(f['kinds'])}")
        print(f"       {r['url']}")
    if len(prose_free) == len(fires) and len(para_zero) == len(fires):
        print(f"\n   -> all four readings say the same thing: every fire is chrome "
              f"a reader\n      never sees, so the 12% is the ninth awakening's "
              f"shape at 43 pages.")
    else:
        print(f"\n   -> {len(fires) - len(both)} fire(s) are not the ninth's "
              f"shape and are the subject of\n      the next measurement, not of "
              f"this census.")

    # -- the cross-checks ---------------------------------------------------
    print(f"\n== the census covers the gate's numerator: "
          f"{len(rows)} pages, {len(census_desync)} disagreement(s)")
    for src, url, gate, kinds_sum in census_desync[:6]:
        print(f"   {src:<12} sup_in_root {gate:,} vs kinds {kinds_sum:,}  {url}")
    if desync:
        print("   the subclass's own census vs the sibling's, where they differ:")
        for src, url, sib, sub in desync[:6]:
            print(f"   {src:<12} sibling {sib:,} vs subclass {sub:,}  {url}")

    # -- the control: what the readings that ignore chrome text do here -----
    # The consequence of the census is already measured on the family's sample
    # (the eleventh: `ptext` catches 18 of 20 with 0 fires on 62 honest pages).
    # This is the same control on the sample that fires 43 times, and it is the
    # number a replacement rule is judged by before its fuzz is run: on the very
    # pages the shipped gate relaxes on, how many of the other readings relax?
    print(f"\n== the same sample, every reading's own fires")
    for k in ("shipped_fires", "span_fires", "ppara_fires", "punion_fires",
              "plist_fires", "ptext_fires", "open_fires"):
        n = [r for r in rows if r[k]]
        print(f"   {k.replace('_fires', ''):<8} {len(n):>3} of {len(rows)}"
              + ("" if not n else "   " + ", ".join(
                  f"{r['src']} {r['shipped_share'] * 100:.0f}%" for r in n[:4])))

    print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<12} {why:<40} {url}")
    print(f"\n   sample digest {digest}")


if __name__ == "__main__":
    main()
