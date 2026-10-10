#!/usr/bin/env python
"""The band under the gate's threshold: is that case a family, or one page?

The twenty-sixth awakening left this named and unmeasured. In the extended
sample (74 measurable pages, digest ``d852e67a98f1e413``) a mutation of
``Parish_of_Coyurunda`` was a *real* truncation — the strict pass lost more than
half of what the clean page returned — and no reading saw it: ``kept`` 621
against ``in_root`` 489, and the gate's judgment is ``sup_in_root > kept``. The
loss was inside the root, it was enormous for the page, and it was still smaller
than what survived. The thread's question is the right shape:

    *how many real truncations remain with `in_root` between half and all of
    `kept` — is it a family, or is it a case?*

That is not a question about a counter, it is a question about a **threshold**,
and it can be answered without re-typing the fuzz. `probe_gate_pos` already
computes, for every real truncation, the two numbers the judgment is made of
(``kept`` and ``sup_in_root``), scores every candidate it is given, and grades
against the page. So this probe does what the twenty-fifth and twenty-sixth did:
it wraps the sibling's ``candidates`` and extends its ``CANDIDATES`` — the
sibling's truth, rounds, order and digest stay its own — with a ladder of rungs
that are the shipped judgment with its threshold moved:

    shipped   sup_in_root > kept         (share > 50%)
    half      sup_in_root > kept / 2     (share > 33%)   — "threw away more than
    third     sup_in_root > kept / 3     (share > 25%)      half of what it kept"
    quarter   sup_in_root > kept / 4     (share > 20%)

Each rung is the same reading, the same region and the same floor, and differs
from the shipped gate only in how much loss the judgment calls a truncation. The
ladder then answers both halves of the question at once:

* **is it a family?** the misses shrink as the threshold drops —
  ``missed(shipped) - missed(half)`` is literally the number of real truncations
  whose loss landed in the band (kept/2, kept];
* **what does it cost?** every rung is scored on the same two numbers as the
  shipped gate (``no-cost`` relaxations under mutation, ``partial``, and fires on
  the honest corpus) *and* this probe prints the honest side directly: the
  corpus's own shares, sorted, so "the price of a threshold" is a list of pages
  and not a feeling.

The honest side is the part that decides, and it has to be read first. The gate
already relaxes once on the honest corpus — Torrebaja, whose share is above 50%
— so the threshold's low end is not free: it is occupied by a page the gate is
already wrong about. What is not known is where the *other* honest pages sit
between p90 (22.4%) and that maximum. If honest pages live in the band, the band
is not a fixable gap and this probe says so with names; if the band is empty of
honest pages, the threshold is a lever and the numbers say how far it can move.

Run:  python tests/probe_band.py [--fuzz N] [--order=url] [--extended] [--list PATH]

`--list PATH` swaps the corpus for another declared sample (`tests/build_corpus.py`
builds one from the same sources: a die roll and today's front pages, neither of
them mine). It is the sample-size lever: the band being empty is a claim about
*how many pages* were drawn, and a bigger sample answers it directly. The digest
that `pin_order` prints is what says whether the run's pages are the family's or
another set.

**Measured, and the answer is one case, not a family.** On the sibling's own
sample (63 pages, digest ``24455059b09c0ea1``, 1,500 rounds) the band is empty:
``shipped`` misses 1 real truncation and every rung misses that same one —
``readrare.com``, ``in_root`` 0, a structural zero no threshold can reach. On the
extended sample (74 pages, digest ``d852e67a98f1e413``) ``shipped`` misses 3 and
the answer is sharper:

    Parish_of_Coyurunda   clean 1,395  kept 621  lost 774  in_root 489  share 44.1%   (kept/in_root 1.27x)
    blog.janestreet.com    clean 11,161 kept 838  lost 10,323 in_root 55  share  6.2%   (kept/in_root 15.24x)
    purplesyringa.moe      clean 5,351  kept 1,768 lost 3,583  in_root  0  share  0.0%   (no region)

Exactly **one** of the three sits in the band (kept/2, kept] — the threshold's
lever can reach one case, and the case is the one the twenty-sixth named. The
other two have no numerator to move: the janestreet variant's numerator is 15x
smaller than what survived, and the third's is zero by construction (it is the
rootless page the twenty-sixth's own branch already ships as
``trunc-root:67%``; the *predicate* cannot fire, the *ladder* does).

**And the price of the rung that reaches it is the band it opens, on both sides:**

    threshold              honest fires (74 pages)      fuzz: caught  missed  silent  no-cost  partial
    shipped  share > 50%   1  (Torrebaja, 54.5%)        19            3       0/2     23       12
    half     share > 33%   1  (the same page)  — +0     20            2       1/2     24       20
    third    share > 25%   6  — +5 honest pages         20            2       1/2    103       39
    quarter  share > 20%   10 — +9 honest pages         20            2       1/2    210       58

The rung that catches ``Parish`` costs **0 honest pages** — the band
(33.3%, 50%] is empty in this corpus — and **+1 no-cost relaxation** in 1,500
mutations, and it loses no capture. Below it the lever stops being cheap: 5
honest pages and 103 no-cost fires for zero further captures. The corpus's own
shares have a gap between **28.8% and 54.5%**, and the shipped threshold sits
inside it — which is why the band is free — while the low bands are not empty at
all (5 pages in (25%, 33%], 4 in (20%, 25%]), so the emptiness above 28.8% is a
property of this sample and not of "the corpus has no pages around there".

That is the honest reading of the price, and it does not by itself justify moving
the gate: the gain is one case of twenty-two on one 74-page sample, and the
eleventh-costume lesson (`a page at 40% would appear tomorrow`) applies to a
band defined by a gap in a sample. What the measurement *does* settle is where
the remaining misses are not: **two of the three have no numerator, so the
threshold is not the fix for them** — the region branches of the twenty-fourth,
twenty-fifth and twenty-sixth were, and after them the residual is this.

**Dating, which this probe also produced:** the twenty-sixth published sample A's
``reales 22, silentes 3`` and that is the number *before* its own fix. The same
sample, same N, same digest (``d852e67a98f1e413``) with the fix gives **silent 2**:
``purplesyringa`` now ships as ``trunc-root:67%`` instead of ``parse=strict``, and
only ``Parish`` and the janestreet variant are still silent. Its journal had the
before/after pair for sample B and only the *before* for A; this is A's pair.

**The twenty-eighth awakening asked the question the thread left — and the gap
did not survive.** ``--list tests/corpus/band_urls.txt`` (363 urls, 353 measurable pages,
digest ``e8d5df572463cd5c``, the census is order-invariant) gives
**max 89.2% · p90 53.9% · median 17.7%**, and the bands are
**43 / 57 / 35 / 19** — the band (33.3%, 50%] that was empty holds **57** honest
pages. So the emptiness above 28.8% was a fact about *19 Wikipedia pages*, and
the twenty-seventh's own warning applies to itself: a band defined by a gap in a
sample closes with the next roll.

But "the gap closed" is the wrong lesson, and the by-source census is what
corrects it: **a distribution is the mixture's**. Same probe, one row per source:

    sample            source       n     max    p90   median  fires  bands
    the family's 74   hn          25   28.8%  14.9%    0.0%     0   0/ 0/ 2/ 0
                      lobsters    22   19.8%   4.1%    0.0%     0   0/ 0/ 0/ 0
                      the nine     9   22.4%    ...      ...     0
                      wikirandom  19   54.5%  27.8%   19.1%     1   1/ 0/ 3/ 3
    the new 353       hn          15   14.5%   9.8%    0.5%     0   0/ 0/ 0/ 0
                      lobsters    22   19.8%   4.1%    0.0%     0   0/ 0/ 0/ 0
                      wikirandom 316   89.2%  55.3%   19.8%    43  43/57/35/19

The gap was inside *one* source: nineteen draw-of-a-die pages, three of them in
(25%, 33.3%], one above 50%, none in between. With 316 of those same pages the
distribution is continuous from 20% to 89% — no gap, no threshold to sit in one.

And the price of the rung that `Parish` paid for is not free: the `half` rung
would take the honest fires from **43 to 100** on this sample (the shipped gate
relaxes on 43 of 353 honest pages — 12%, **every one of them Wikipedia**), for
one case of twenty-two. On the front-page sources the shipped gate fires **0 of
37**, exactly as before: the false-positive rate was never 1 in 62, it was 1 in
19 Wikipedia pages, and the ninth awakening's own corpus was three parts
front-page links to one part die roll.

That is the measurement, and the honest reading of it is *two* things at once:
the threshold move is refused with a price that is 57 pages wide, and the corpus
question — the oldest open item of this family — is not "how big" but **"of
what"**, because the mixture decides the tail a threshold is compared against.
"""
import importlib.util
import os
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402


def _load_sibling(name: str):
    path = os.path.join(HERE, "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# (name, divisor) — the shipped judgment `sup_in_root > kept` with `kept`
# divided. The words are the ones the gate's own docstring uses: "more thrown
# away than kept".
RUNGS = (("half", 2), ("third", 3), ("quarter", 4))


def patch(module):
    """Add the rungs as candidates; change nothing else about the sibling.

    A rung fires exactly like `shipped` does, on the same two numbers, with the
    same floor — the only difference is the multiplier. It is added as a row so
    the sibling's own fuzz scores it with the sibling's own truth (`lost > half
    of the clean page`), which is a truth no rung can grade.
    """
    inner = module.candidates

    def candidates_with_rungs(html):
        c = inner(html)
        kept, sup, floor = c["kept"], c["sup_in_root"], keyhole.EMPTY_TEXT
        for name, k in RUNGS:
            c[f"{name}_fires"] = sup * k > kept and sup > floor
        return c

    module.candidates = candidates_with_rungs
    module.CANDIDATES = tuple(module.CANDIDATES) + tuple(n for n, _ in RUNGS)
    return candidates_with_rungs


def _share(r, key="sup_in_root"):
    kept, sup = r["kept"], r[key]
    region = kept + sup
    return (sup / region) if region else 0.0


def _rung_share(k):
    """The share a rung's threshold sits at: sup > kept/k  <=>  share > 1/(k+1)."""
    return 1.0 / (k + 1.0)


def _print_skipped(skipped) -> None:
    """The pages the sample does not contain, named.

    The twenty-eighth awakening only asked this function to exist because the
    census-only path (`probe_band.py --extended`, no `--fuzz`) printed the
    header ``left out (10)`` and **no rows**: a count with no names, in the same
    file whose whole subject is that a count is not a measurement. Two exits —
    one at the end of the fuzz, one before it — and only one of them named. Now
    there is one printer and both exits call it.
    """
    print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<12} {why:<40} {url}")


def main():
    rounds = 0
    if "--fuzz" in sys.argv:
        i = sys.argv.index("--fuzz")
        rounds = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 1500
    pg = _load_sibling("probe_gate")
    pr = _load_sibling("probe_rules")
    gpos = _load_sibling("probe_gate_pos")
    candidates = patch(gpos)
    floor = keyhole.EMPTY_TEXT
    extended = "--extended" in sys.argv

    # `--list PATH` swaps the corpus for another declared sample. It is the
    # sample-size lever the twenty-eighth awakening needs: the band (33.3%,
    # 50%] being empty is a fact about 74 pages, and a gap in a sample of 74
    # closes with the next roll — so the question is asked again on a corpus an
    # order of magnitude larger (`tests/build_corpus.py`, same sources: a die
    # roll and today's front pages, neither of them mine). The sibling's guard
    # below is unchanged, so the sample is still the sibling's shape; the digest
    # is what says whether this run's pages are the family's or another set.
    if "--list" in sys.argv:
        path = sys.argv[sys.argv.index("--list") + 1]
        urls = pg.read_list(path)
        provenance = path
    else:
        urls = (pg.read_list(gpos.DEFAULT_LIST)
                + [(f"old-{n}", u) for n, u in
                   [(s.replace(".", ""), u) for s, u in pr.SITES]])
        provenance = "uncurated + the nine the gate was built on"
    print(f"keyhole {keyhole.__version__} — the band under the gate's threshold\n"
          f"corpus: {len(urls)} urls ({provenance})"
          f"   floor {floor}\n")

    rows, skipped = [], []
    for src, url in urls:
        if not pg.is_html(url):
            skipped.append((src, url, "not html"))
            continue
        try:
            html = pg.cached_download(url)
        except Exception as e:
            skipped.append((src, url, f"{type(e).__name__}"[:30]))
            continue
        c = candidates(html)
        # The sibling's own guard, kept identical so the sample is its sample:
        # if the digest below is not `24455059b09c0ea1`, this probe is measuring
        # a different corpus and nothing here is comparable to the family.
        #
        # `--extended` is the twenty-sixth awakening's separation instead: the
        # two exclusion reasons are not the same fact, so only the floor (a fact
        # about the page) excludes here, and a page with no root at all — a fact
        # about the tool — stays in the corpus the gate should be judged on. The
        # sample it produces is the 74 measurable pages whose digest that
        # awakening declared (`d852e67a98f1e413`); if this run prints another
        # digest, it is another sample and says so.
        if c["kept"] < floor or (not extended and not c["scope"]):
            skipped.append((src, url, f"no region ({c['kept']} kept, "
                                      f"scope {c['scope'] or 'none'})"))
            continue
        rows.append({"src": src, "url": url, **c})

    digest = gpos.pin_order(rows, sys.argv)

    # -- the honest side, which is the price ---------------------------------
    print(f"\n== the honest corpus: where its own shares fall ({len(rows)} pages)")
    print(f"   the thresholds a share has to cross:  "
          + "   ".join(f"{n} {_rung_share(k) * 100:.1f}%"
                       for n, k in (("shipped", 1),) + RUNGS))
    hon = {name: [r for r in rows if r[f"{name}_fires"]]
           for name in ("shipped",) + tuple(n for n, _ in RUNGS)}
    for name, r_ in hon.items():
        print(f"   {name:<8} fires {len(r_):>2}  "
              + (", ".join(f"{r['src']} {_share(r) * 100:.1f}%" for r in r_) or "-"))
    cells = (("shipped", 1),) + RUNGS
    for i, (name, k) in enumerate(cells):
        lo = _rung_share(k)
        hi = _rung_share(cells[i - 1][1]) if i else 1.0
        band = [r for r in rows if lo < _share(r) <= hi]
        print(f"   band ({lo * 100:.1f}%, {hi * 100:.1f}%]: {len(band):>2} honest "
              f"page(s)" + ("" if not band else "  <-- the price of that rung"))
        for r in band:
            print(f"     {r['src']:<12} share {_share(r) * 100:>5.1f}%  "
                  f"kept {r['kept']:>7,}  in_root {r['sup_in_root']:>7,}  {r['url']}")
    shares = sorted((_share(r) for r in rows), reverse=True)
    print(f"   share distribution:  max {shares[0] * 100:.1f}%  "
          f"p90 {shares[int(len(shares) * .1)] * 100:.1f}%  "
          f"median {statistics.median(shares) * 100:.1f}%  "
          f"p10 {shares[int(len(shares) * .9)] * 100:.1f}%")
    print(f"   worst ten pages by share:")
    for r in sorted(rows, key=lambda r: -_share(r))[:10]:
        print(f"     {r['src']:<12} share {_share(r) * 100:>5.1f}%  "
              f"kept {r['kept']:>7,}  in_root {r['sup_in_root']:>7,}  "
              f"rung {r['rung']}")

    # -- the same census, split by where the page came from -------------------
    # The twenty-eighth awakening asked this question of a corpus ten times
    # larger and the gap did not survive. The reason it did not is not a fact
    # about the web: a sample drawn from a *mixture* of sources has a share
    # distribution that is the mixture's, and the previous corpus was three
    # parts front-page links to one part die roll while this one is roughly the
    # other way round. That is a measurement, not an explanation, so it gets
    # its own table: same quantity, same probe, one row per source. A page
    # whose source cannot be named would be a row here before it is a total.
    print(f"\n== the same census, by source — a distribution is the mixture's")
    for src in sorted({r["src"] for r in rows}):
        grp = [r for r in rows if r["src"] == src]
        sh = sorted((_share(r) for r in grp), reverse=True)
        fires = [r for r in grp if r["shipped_fires"]]
        bands = []
        for i, (name, k) in enumerate(cells):
            lo, hi = _rung_share(k), (_rung_share(cells[i - 1][1]) if i else 1.0)
            bands.append(sum(1 for r in grp if lo < _share(r) <= hi))
        print(f"   {src:<12} n {len(grp):>3}  max {sh[0] * 100:>5.1f}%  "
              f"p90 {sh[int(len(sh) * .1)] * 100:>5.1f}%  "
              f"median {statistics.median(sh) * 100:>5.1f}%  "
              f"fires {len(fires):>3}  bands "
              + "/".join(f"{b:>3}" for b in bands))
    print(f"   (bands are the four above, top to bottom: >50% / 33.3-50% / "
          f"25-33.3% / 20-25%)")

    if not rounds:
        _print_skipped(skipped)
        return

    # -- the fuzz, scored by the sibling --------------------------------------
    pages, clean_kept = [], []
    for r in rows:
        try:
            html = pg.cached_download(r["url"])
        except Exception:
            continue
        pages.append((html, r["src"], r["url"]))
        clean_kept.append(candidates(html)["kept"])
    f = gpos.fuzz(pages, clean_kept, rounds)

    names = ("shipped",) + tuple(n for n, _ in RUNGS)
    print(f"\n== fuzz {rounds} mutations on the sibling's own sample "
          f"(digest {digest})")
    print(f"   mutations scored {f['n']}   real truncations {f['real']}"
          f"   of those silent (parse=strict) {f['silent']}")
    print(f"   {'':<8} {'caught':>7} {'missed':>7} {'silent':>8} "
          f"{'no-cost':>8} {'partial':>8}")
    for k in names:
        print(f"   {k:<8} {f[k]['caught']:>7} {f[k]['missed_real']:>7} "
              f"{f[k]['silent_caught']:>3}/{f['silent']:<4} "
              f"{f[k]['zero_cost']:>8} {f[k]['partial']:>8}")
    m = {k: f[k]["missed_real"] for k in names}
    print(f"\n== the band, which is the question: real truncations no rung reaches")
    prev = m["shipped"]
    print(f"   more was thrown than kept (shipped):  missed {prev}")
    for name, k in RUNGS:
        print(f"   ...than kept/{k} ({name:<7}):  missed {m[name]}"
              f"   -> {prev - m[name]} real case(s) in the band above it")
        prev = m[name]

    def _miss_line(ex, extra=""):
        kept, sup = ex["kept"], ex["in_root"]
        region = kept + sup
        ratio = f"{kept / sup:.2f}x" if sup else "  inf"
        return (f"   {ex['label']:<12} clean {ex['clean']:,} kept {kept:,} "
                f"(lost {ex['lost']:,})  in_root {sup:,}  "
                f"share {100 * sup / region if region else 0:5.1f}%  "
                f"kept/in_root {ratio}  rung {ex['rung']}{extra}\n"
                f"     {ex['url']}")

    print(f"\n== named: every real truncation the shipped gate misses")
    for ex in f["shipped"]["examples"]:
        zero = ("" if ex["in_root"] else
                "   <-- structural zero: no region to divide by, so no threshold"
                " on in_root can ever reach it")
        print(_miss_line(ex, zero))
    for name in (n for n, _ in RUNGS):
        for ex in f[name]["examples"]:
            print(f"   still missed by {name:<8}:\n{_miss_line(ex)}")

    _print_skipped(skipped)


if __name__ == "__main__":
    main()
