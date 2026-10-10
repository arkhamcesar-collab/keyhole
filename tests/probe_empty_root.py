#!/usr/bin/env python
"""The price of the fix, measured before building it: a gate with two regions.

The twenty-fourth awakening found the shape the region family cannot see. On
`readrare.com` the shipped gate's numerator lives inside `<main class="case">`,
which is an empty shell the JS fills — `scope = empty-root` — so every reading
that attributes the loss to a frame *inside the root* returns 0 there, not
because it is blind but because the region does not exist. In the pinned fuzz that
page is the single real truncation the shipped gate loses, and the only one that
ships **silently** (`parse=strict`), which is exactly the shape the gate exists to
catch. `span` (both passes, whole page) catches it; `span` is not shipped.

The candidate that follows is one sentence: **when `scope` is `empty-root`, the
gate judges the whole-page delta (`span`) instead of the delta inside the root.**
It is a *hybrid*, and the number that decides it is not in the fuzz. It is the
honest corpus: the shipped gate fires on 1 of 63 honest pages and `span` fires on
1, so the first question is whether they are **the same fire**. If they are, the
hybrid costs nothing where it applies (the two empty-root pages do not fire under
`span` either) and buys the one silent miss back; if not, the fix buys a false
positive on a page nobody damaged, which is the Torrebaja error in a new region.

So this probe measures the hybrid the way the family measures everything: on the
honest corpus for its price, and in the fuzz for what it buys. It does not
re-type the fuzz — it loads `probe_gate_pos`, asks *its* `candidates()` for the
numbers, and appends the hybrid as one more row, so `real`, `silent` and the
grading truth are the same instrument that scored the twenty-third and
twenty-fourth awakenings. Two regions in one gate is a change to `keyhole.py`;
this is the measurement that has to exist first, and it is allowed to say no.

Run:  python tests/probe_empty_root.py [--fuzz N] [--order=url]
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402

_pg = None


def _load_sibling(name: str):
    path = os.path.join(HERE, "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hybrid_fires(c: dict) -> bool:
    """One gate, two declared regions.

    The rule the twenty-fourth awakening left to measure: on a page whose region
    is empty the in-root share is arithmetic (0.0% before and after the same
    mutation), so the gate has to judge the page instead. Everywhere else it is
    the shipped rule, unchanged — the hybrid is not a new counter, it is the
    shipped one with a second region for the pages where the first one is empty.
    """
    if c["scope"] == keyhole.SCOPE_EMPTY_ROOT:
        return bool(c["span_fires"])
    return bool(c["shipped_fires"])


def patch(module):
    """Add the hybrid row to the sibling's fuzz without touching its file.

    `probe_gate_pos.fuzz` looks up `candidates` and `CANDIDATES` in its own
    module namespace, so wrapping the one and extending the other is enough for
    the fuzz to score the hybrid with its own truth, its own mutation loop and
    its own pinned order. A probe that re-types the fuzz is the second-costume
    sin: it agrees with its sibling by accident.
    """
    inner_candidates = module.candidates
    inner_fuzz = module.fuzz

    def candidates_with_hybrid(html):
        c = inner_candidates(html)
        c["hybrid_fires"] = _hybrid_fires(c)
        return c

    module.candidates = candidates_with_hybrid
    module.CANDIDATES = tuple(module.CANDIDATES) + ("hybrid",)
    return candidates_with_hybrid, inner_fuzz


def main():
    global _pg
    rounds = 0
    if "--fuzz" in sys.argv:
        i = sys.argv.index("--fuzz")
        rounds = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 1500
    _pg = _load_sibling("probe_gate")
    _pr = _load_sibling("probe_rules")
    gpos = _load_sibling("probe_gate_pos")
    candidates, fuzz = patch(gpos)
    floor = keyhole.EMPTY_TEXT

    urls = _pg.read_list(gpos.DEFAULT_LIST) + [
        (f"old-{n}", u) for n, u in
        [(s.replace(".", ""), u) for s, u in _pr.SITES]]
    print(f"keyhole {keyhole.__version__} — the price of a gate with two "
          f"regions\ncorpus: {len(urls)} urls (uncurated + the nine the gate "
          f"was built on)\n")

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
            skipped.append((src, url,
                            f"no region ({c['kept']} kept, scope "
                            f"{c['scope'] or 'none'})"))
            continue
        rows.append({"src": src, "url": url, **c})

    gpos.pin_order(rows, sys.argv)

    # -- the honest corpus: what the hybrid costs -----------------------------
    blind = [r for r in rows if r["scope"] == keyhole.SCOPE_EMPTY_ROOT]
    print(f"== honest corpus: {len(rows)} measurable pages, "
          f"{len(blind)} of them with an empty region")
    print(f"\n   the empty-region pages, and what `span` reads there — the "
          f"whole-page delta the hybrid would use:")
    print(f"   {'src':<12} {'kept':>8} {'no-chrome':>10} {'page delta':>11} "
          f"{'span':>7} {'span fires':>10}   url")
    for r in blind:
        delta = r["kept_nc"] - r["kept"]
        print(f"   {r['src']:<12} {r['kept']:>8,} {r['kept_nc']:>10,} "
              f"{delta:>11,} {r['span_share'] * 100:>6.1f}% "
              f"{('YES' if r['span_fires'] else 'no'):>10}   {r['url']}")

    fired = {k: [r for r in rows if r[k]] for k in
             ("shipped_fires", "span_fires", "hybrid_fires")}
    print(f"\n   fires on the honest corpus:  "
          + "   ".join(f"{k.replace('_fires', '')} {len(v)}"
                       for k, v in fired.items()))
    for k, v in fired.items():
        for r in v:
            print(f"     {k.replace('_fires', ''):<7} fires: {r['url']}  "
                  f"scope {r['scope'] or 'none'}  kept {r['kept']:,}  "
                  f"in_root {r['sup_in_root']:,}")
    same = (sorted(r["url"] for r in fired["shipped_fires"])
            == sorted(r["url"] for r in fired["span_fires"]))
    print(f"   the two counters fire on the same page(s): "
          f"{'YES' if same else 'NO'}")

    added = [r for r in rows if r["hybrid_fires"] and not r["shipped_fires"]]
    lost = [r for r in rows if r["shipped_fires"] and not r["hybrid_fires"]]
    print(f"\n   hybrid vs shipped, page by page: "
          f"{len(added)} relaxation added, {len(lost)} relaxation dropped")
    for r in added:
        print(f"     ADDED   {r['src']:<12} {r['url']}  kept {r['kept']:,}  "
              f"no-chrome {r['kept_nc']:,}  scope {r['scope'] or 'none'}")
    for r in lost:
        print(f"     DROPPED {r['src']:<12} {r['url']}  kept {r['kept']:,}  "
              f"in_root {r['sup_in_root']:,}  scope {r['scope'] or 'none'}")
    if not added and not lost:
        print("     (identical to the shipped gate on every honest page: the "
              "hybrid's second region costs nothing where it applies)")

    # -- the fuzz: what the hybrid buys ---------------------------------------
    if rounds:
        pages, clean_kept = [], []
        for r in rows:
            try:
                html = _pg.cached_download(r["url"])
            except Exception:
                continue
            pages.append((html, r["src"], r["url"]))
            clean_kept.append(candidates(html)["kept"])
        print(f"\n== fuzz: {rounds} mutations that open a suppression inside "
              f"the root (the sibling's loop, its truth, its order)")
        f = fuzz(pages, clean_kept, rounds)
        print(f"   mutations scored:                     {f['n']}")
        print(f"   the mutation really ate the article:  {f['real']}")
        print(f"   of those, SILENT (parse=strict):      {f['silent']}   <-- what "
              f"the gate exists to catch")
        print(f"   of those, on a page whose region is empty: {f['blind']}"
              f"   <-- the hybrid's reason to exist")
        for label, url, clean, kept, kept_nc, scope in f["blind_named"]:
            print(f"     {label:<12} {url}\n"
                  f"       clean {clean:,} kept {kept:,} no-chrome {kept_nc:,} "
                  f"scope {scope}")
        print(f"\n   {'':<8} {'caught':>7} {'missed':>7} {'silent':>8} "
              f"{'no-cost':>8} {'partial':>8}")
        for k in ("shipped", "span", "hybrid", "ptext", "punion"):
            print(f"   {k:<8} {f[k]['caught']:>7} {f[k]['missed_real']:>7} "
                  f"{f[k]['silent_caught']:>3}/{f['silent']:<4} "
                  f"{f[k]['zero_cost']:>8} {f[k]['partial']:>8}")
        for k in ("hybrid", "shipped"):
            for ex in f[k]["examples"]:
                print(f"   {k} MISSED: {ex['label']} {ex['url']}\n"
                      f"      clean {ex['clean']:,} kept {ex['kept']:,} "
                      f"(lost {ex['lost']:,})  no-chrome {ex['kept_nc']:,}  "
                      f"rung {ex['rung']}  scope {ex['scope'] or 'none'}  "
                      f"in_root {ex['in_root']:,}")

    print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<12} {why:<40} {url}")


if __name__ == "__main__":
    main()
