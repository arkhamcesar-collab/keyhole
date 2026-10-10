#!/usr/bin/env python
"""The pages with no root at all: the second exclusion reason the corpus hid.

The twenty-fifth awakening closed the empty-*region* case in `_parse` and left
the empty-*root* case written off in one sentence: *a page with no root at all
(`scope` falsy) has the same empty numerator and is deliberately not covered —
the measured corpus has 13 of those and every one is outside the floor, so
applying this to them would be an unmeasured change.*

The first half is right and the second half is false, and it is false in the
direction that matters. Of those 13 pages, **11 are above the floor of 200** —
they are the four largest pages in the whole corpus (47,507 · 33,121 · 16,181 ·
15,916 characters) plus seven mid-sized ones. They were never excluded by the
floor. They were excluded by the probe's own guard, which bundles two different
facts into one `continue`:

    if c["kept"] < floor or not c["scope"]:
        skipped.append(...)

`kept < floor` is a fact about the page (too little text to judge a share).
`not c["scope"]` is a fact about the *tool* — it has no region here. Bundling
them deleted the eleven biggest pages from a corpus whose whole purpose is to
judge the gate, and left a sentence in the shipped docstring saying the floor had
done it. That is the ninth costume of the same sin, and the first one found in the
*sample* rather than in a counter: a corpus that drops pages by a rule it
attributes to a different rule.

What is at stake on those pages is not small. With no root frame open,
`_in_root_region()` is false everywhere, so `sup_in_root` is 0 by construction and
`ate_the_root` reads `0 > kept` — false on every one of them, honest or mutated.
The gate has no region there for the same reason it had none on `readrare.com`,
only larger: a mutation that eats 40,000 characters of a 47,507-character page
ships as `parse=strict`. The twenty-fifth's branch asks the whole-page delta
*where the region is empty*. This probe asks the same question where the region
never existed, and prices it before anyone writes it.

The discipline is the family's. The fuzz is not re-typed: `probe_gate_pos`'s
`fuzz`, its truth, its mutation loop and its `pin_order` score everything here,
with two rows appended the same way the twenty-fifth appended one (wrap
`candidates`, extend `CANDIDATES`). Two samples are run and both say their digest:

* **A** — every page the corpus can measure once both reasons are named
  (63 + the 11 above the floor), which is the corpus the gate should have been
  judged on;
* **B** — the 11 rootless pages alone, its own sample and its own digest, so "how
  much of the mutant damage lands on a page the gate cannot see" is a number and
  not an inference.

Neither run is comparable to the twenty-fifth's 63-page numbers — the sample
changed, which is exactly what a digest is for. What *is* comparable inside each
run is the gate against itself: the sample is pinned on the URL, so it does not
move when the counter does. And by the same argument a run of this probe is
comparable to **another run of this probe** (same digests, `random.Random(0)`,
same N), which is how the fix's effect is read: before it, three real truncations
on the rootless sample ship silently; after it, none do.

Run:  python tests/probe_no_root.py [--fuzz N] [--order=url] [--sample=ab|a|b]
"""
import importlib.util
import os
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


def _regionless(c: dict) -> bool:
    """True where the shipped gate has no region to divide by.

    Two ways to have none, and the twenty-fifth only covered the first: a root
    was found and the cut kept nothing (`empty-root`), or no root was found at
    all (`scope` falsy). In both cases `sup_in_root` is 0 on the honest page and
    0 on the page a frame ate half of — the same zero twice, which is arithmetic.
    """
    return (not c["scope"]) or c["scope"] == keyhole.SCOPE_EMPTY_ROOT


def patch(module):
    """Add two rows to the sibling's fuzz without touching its file.

    `hybrid` is the twenty-fifth's rule exactly (empty region only) and is here
    to show it is *unchanged* where both apply; `hybrid2` is the same rule with
    the second way of having no region added. Wrapping `candidates` and extending
    `CANDIDATES` is enough: the sibling's `fuzz` looks both up in its own module
    namespace, so its truth, its rounds and its order stay its own.
    """
    inner_candidates = module.candidates
    inner_fuzz = module.fuzz

    def candidates_with_hybrids(html):
        c = inner_candidates(html)
        c["hybrid_fires"] = (bool(c["span_fires"])
                             if c["scope"] == keyhole.SCOPE_EMPTY_ROOT
                             else bool(c["shipped_fires"]))
        c["hybrid2_fires"] = (bool(c["span_fires"]) if _regionless(c)
                              else bool(c["shipped_fires"]))
        return c

    module.candidates = candidates_with_hybrids
    module.CANDIDATES = tuple(module.CANDIDATES) + ("hybrid", "hybrid2")
    return candidates_with_hybrids, inner_fuzz


def run_fuzz(label, pg, gpos, rows, rounds, argv, keys):
    """One declared sample: pin its order, then the sibling's own fuzz.

    `pin_order` sorts the row dicts and prints the digest; the pages the fuzz
    indexes into are built *after* that sort, so the same index is the same page
    for every candidate scored below.
    """
    if not rounds:
        return
    gpos.pin_order(rows, argv)
    pages, clean_kept = [], []
    for r in rows:
        try:
            html = pg.cached_download(r["url"])
        except Exception:
            continue
        pages.append((html, r["src"], r["url"]))
        clean_kept.append(gpos.candidates(html)["kept"])
    f = gpos.fuzz(pages, clean_kept, rounds)
    print(f"\n== fuzz {label}: {rounds} rounds, {len(pages)} pages in the sample")
    print(f"   {'':<8} {'caught':>7} {'missed':>7} {'silent':>8} "
          f"{'no-cost':>8} {'partial':>8}")
    for k in keys:
        print(f"   {k:<8} {f[k]['caught']:>7} {f[k]['missed_real']:>7} "
              f"{f[k]['silent_caught']:>3}/{f['silent']:<4} "
              f"{f[k]['zero_cost']:>8} {f[k]['partial']:>8}")
    print(f"   mutations scored {f['n']}   real {f['real']}   silent {f['silent']}"
          f"   on a page whose region is empty {f['blind']}")
    for label_, url, clean, kept, kept_nc, scope in f["blind_named"]:
        print(f"     regionless: {label_:<12} clean {clean:,} kept {kept:,} "
              f"no-chrome {kept_nc:,} scope {scope or 'none'}\n       {url}")
    for k in ("shipped", "hybrid2"):
        for ex in f[k]["examples"]:
            print(f"   {k} MISSED: {ex['label']} {ex['url']}\n"
                  f"      clean {ex['clean']:,} kept {ex['kept']:,} "
                  f"(lost {ex['lost']:,})  no-chrome {ex['kept_nc']:,}  "
                  f"rung {ex['rung']}  scope {ex['scope'] or 'none'}  "
                  f"in_root {ex['in_root']:,}")
    return f


def main():
    rounds = 0
    if "--fuzz" in sys.argv:
        i = sys.argv.index("--fuzz")
        rounds = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 1500
    pg = _load_sibling("probe_gate")
    pr = _load_sibling("probe_rules")
    gpos = _load_sibling("probe_gate_pos")
    candidates, fuzz = patch(gpos)
    gpos.fuzz = fuzz
    floor = keyhole.EMPTY_TEXT

    urls = (pg.read_list(gpos.DEFAULT_LIST)
            + [(f"old-{n}", u) for n, u in
               [(s.replace(".", ""), u) for s, u in pr.SITES]])
    print(f"keyhole {keyhole.__version__} — the pages with no root at all\n"
          f"corpus: {len(urls)} urls (uncurated + the nine the gate was built on)"
          f"   floor {floor}\n")

    rows, no_root, small, other = [], [], [], []
    for src, url in urls:
        if not pg.is_html(url):
            other.append((src, url, "not html"))
            continue
        try:
            html = pg.cached_download(url)
        except Exception as e:
            other.append((src, url, f"{type(e).__name__}"[:30]))
            continue
        c = candidates(html)
        r = {"src": src, "url": url, **c}
        if not c["scope"]:
            (no_root if c["kept"] >= floor else small).append(r)
        elif c["kept"] < floor:
            small.append(r)
        else:
            rows.append(r)

    # -- the two exclusion reasons, separated --------------------------------
    print(f"== the two reasons the guard bundles into one `continue`")
    print(f"   kept < {floor} (a fact about the page):              "
          f"{len([r for r in small])}")
    print(f"   no root at all (a fact about the tool):             "
          f"{len(no_root) + len([r for r in small if not r['scope']])}")
    print(f"     of those, above the floor — dropped by the guard, not the floor: "
          f"{len(no_root)}")
    print(f"     of those, below the floor — the floor would have dropped them: "
          f"{len([r for r in small if not r['scope']])}")
    print(f"   measurable (scope + floor):                         {len(rows)}")
    print(f"\n   the no-root pages above the floor — the corpus's four largest "
          f"pages among them:")
    print(f"   {'src':<12} {'kept':>8} {'no-chrome':>10} {'page delta':>11} "
          f"{'shipped':>8} {'span':>6} {'in_root':>8}   url")
    for r in sorted(no_root, key=lambda r: -r["kept"]):
        d = r["kept_nc"] - r["kept"]
        print(f"   {r['src']:<12} {r['kept']:>8,} {r['kept_nc']:>10,} "
              f"{d:>11,} {('YES' if r['shipped_fires'] else 'no'):>8} "
              f"{('YES' if r['span_fires'] else 'no'):>6} "
              f"{r['sup_in_root']:>8,}   {r['url']}")

    # -- the honest price: what the second region costs where it now applies --
    ext = rows + no_root
    fired = {k: [r for r in ext if r[k]] for k in
             ("shipped_fires", "span_fires", "hybrid_fires", "hybrid2_fires")}
    print(f"\n== honest price on the extended corpus ({len(ext)} measurable "
          f"pages)")
    print("   fires:  " + "   ".join(f"{k.replace('_fires', '')} {len(v)}"
                                     for k, v in fired.items()))
    for k, v in fired.items():
        for r in v:
            print(f"     {k.replace('_fires', ''):<7} fires: {r['url']}  "
                  f"scope {r['scope'] or 'none'}  kept {r['kept']:,}  "
                  f"in_root {r['sup_in_root']:,}")
    added = [r for r in ext if r["hybrid2_fires"] and not r["shipped_fires"]]
    lost = [r for r in ext if r["shipped_fires"] and not r["hybrid2_fires"]]
    same_as_25 = (sorted(r["url"] for r in ext if r["hybrid_fires"])
                  == sorted(r["url"] for r in ext if r["hybrid2_fires"]))
    print(f"   hybrid2 vs shipped: {len(added)} added, {len(lost)} dropped")
    for r in added:
        print(f"     ADDED   {r['src']:<12} {r['url']}  kept {r['kept']:,}  "
              f"no-chrome {r['kept_nc']:,}  scope {r['scope'] or 'none'}")
    for r in lost:
        print(f"     DROPPED {r['src']:<12} {r['url']}  kept {r['kept']:,}")
    print(f"   the twenty-fifth's row fires on the same pages as this one: "
          f"{'YES' if same_as_25 else 'NO'}")

    keys = ("shipped", "span", "hybrid", "hybrid2", "ptext")
    want = "ab"
    for a in sys.argv:
        if a.startswith("--sample="):
            want = a.split("=", 1)[1].lower()
    if rounds:
        # -- A: the corpus the gate should have been judged on ----------------
        if "a" in want:
            run_fuzz(f"A (all measurable, {len(ext)} pages)", pg, gpos, list(ext),
                     rounds, sys.argv, keys)

        # -- B: the rootless pages alone, its own sample ----------------------
        if "b" in want:
            run_fuzz(f"B (no-root pages alone, {len(no_root)} pages)", pg, gpos,
                     list(no_root), rounds, sys.argv, keys)

    print(f"\n== left out ({len(small) + len(other)}) — named, not folded into "
          f"a total")
    for r in small:
        print(f"   {r['src']:<12} under the floor ({r['kept']} kept, "
              f"scope {r['scope'] or 'none':<12})  {r['url']}")
    for src, url, why in other:
        print(f"   {src:<12} {why:<30}  {url}")


if __name__ == "__main__":
    main()
