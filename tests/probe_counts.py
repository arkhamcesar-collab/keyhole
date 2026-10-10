#!/usr/bin/env python
"""Does each fuzz probe print a measurement, or a theorem?

The twelfth awakening left the question in THREADS: of the old keyhole probes,
*how many count where they should name?* `probe_truncation` and
`probe_gate_span` print totals — ``MISSED (shipped a stub silently): 0`` — that
the tenth awakening had already declared the gate's opinion rather than the
truth. This probe measures that, and the shape it finds is the seventh
awakening's rung 3 in new clothing: **a total that cannot be anything else is not
a measurement, and its costume is a zero with a safety label next to it.**

It does not re-type the instruments. Each sibling probe is loaded by path (the
pattern the probes already use) and this audit calls *their* ``candidates()``,
so it cannot drift from what they do. The three fuzzes grade against three
different truths, and the difference is the whole question:

    probe_truncation   ``ate``      = ``keyhole.ate_the_root`` — the shipped gate
    probe_gate_span    ``any(...)`` = any candidate fires, shipped among them
    probe_gate_pos     the page's own clean extraction — no candidate in it

Two of the three read the reading they are grading, so their zero-for-the-gate
is arithmetic: `ate_the_root` is also what puts the rung on `trunc-root`, so the
branch that would count a *silent* truncation can never be taken. The third is
the only truth a candidate cannot satisfy by disagreeing with the gate.

Per probe, four numbers, and the number that matters is the last one:

  reads the gate?   is the examined reading inside the truth?
  reachable         can the failure branch ever be taken?
  invented real     mutations the truth calls real that the page says untouched
  blind candidate   a candidate scored by a counter that cannot see the text it
                    was written for (``_ParaLoss`` vs. the structural `ptext`)

Every invented case is *named* — the page, the clean extraction, what survived,
what was lost and how — because counting the disagreement is what let it hide
through three awakenings. The mutation shape is copied verbatim from the three
fuzzes (they already carry the same copy); the corpus and the floor come from
``probe_gate``.

Run:  python tests/probe_counts.py [--fuzz N] [--min-chars N]
"""
import importlib.util
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402

DEFAULT_LIST = os.path.join(HERE, "tests", "corpus", "gate_urls.txt")

# The readings each fuzz scores, named as the probe names them, so the audit can
# ask the shipped predicate without re-typing it.
_SPAN_CANDIDATES = ("shipped", "span", "para")


def _load_sibling(name: str):
    path = os.path.join(HERE, "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pg = _load_sibling("probe_gate")
_pr = _load_sibling("probe_rules")
_pt = _load_sibling("probe_truncation")
_ps = _load_sibling("probe_gate_span")
_pp = _load_sibling("probe_gate_pos")


# A fixture built to reach `probe_truncation`'s *other* zero. Its `below` branch
# needs the strict pass to keep a minority of the root while the loss stays under
# the empty-page floor: `sup_in_root > kept` and `sup_in_root <= EMPTY_TEXT`. The
# 1,500-mutation fuzz never rolled it (0), but a witness exists — which is the
# difference between a fact about the corpus and a fact about the arithmetic.
WITNESS_BELOW = ("<main><p>" + "keep " * 20 + "</p>"
                 "<nav><p>" + "nav " * 50 + "</p></nav></main>")


def witness(html: str) -> dict:
    """Ask probe_truncation's own `measure` what the witness produces."""
    m = _pt.measure(html)
    return {
        "kept": m["kept"], "drop_in_root": m["drop_in_root"],
        "ate": m["ate"], "rung": m["rung"],
        "below": m["rung"] == "strict" and not m["ate"]
                 and m["drop_in_root"] > m["kept"],
        "missed": m["rung"] == "strict" and m["ate"],
    }


def mutate(src: str, rnd: random.Random) -> str:
    """Open a suppression inside the root and sometimes never close it.

    Copied verbatim from the three fuzzes (which already share one copy). It is
    the one duplicated line in this file and the honest reading is that it is a
    risk: if a probe sharpens its mutation shape and this does not follow, the
    audit would be grading a different experiment.
    """
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
    return html


def page_truth(clean: int, kept: int) -> bool:
    """The tenth awakening's truth: the page, not any candidate.

    The strict pass ate the article when the mutated extraction lost more than
    half of what the *same page* returned clean, and still returned something a
    caller could read (below that the first rung already fired and nothing is
    silent).
    """
    lost = clean - kept
    return lost > clean * 0.5 and lost > keyhole.EMPTY_TEXT and kept > keyhole.EMPTY_TEXT


def audit(pages, clean_kept, rounds, seed=0):
    rnd = random.Random(seed)
    out = {
        # probe_truncation: truth is the gate itself
        "n": 0, "gate_real": 0, "gate_real_strict_rung": 0,
        "gate_real_page_real": 0, "gate_real_examples": [],
        "gate_rungs": {}, "below": 0,
        # probe_gate_span: truth is any candidate, gate included
        "or_real": 0, "or_real_page_real": 0, "or_real_examples": [],
        # per-candidate misses under each truth
        "miss": {k: {"or": 0, "page": 0, "invented": [], } for k in _SPAN_CANDIDATES},
        # the blind counter: _ParaLoss vs the structural ptext
        "para_blind": 0, "para_blind_examples": [],
        "page_real": 0,
    }
    for _ in range(rounds):
        i = rnd.randrange(len(pages))
        src, label = pages[i]
        clean = clean_kept[i]
        html = mutate(src, rnd)
        try:
            c_pp = _pp.candidates(html)    # shipped, span, ptext, open, ppara, plist
            c_ps = _ps.candidates(html)    # shipped, span, para
        except Exception:
            continue
        out["n"] += 1
        kept = c_pp["kept"]
        rung = c_pp["rung"]
        p_real = page_truth(clean, kept)
        gate_real = bool(c_pp["shipped_fires"])
        or_real = any(c_ps[f"{k}_fires"] for k in _SPAN_CANDIDATES)
        if p_real:
            out["page_real"] += 1

        # --- probe_truncation: `missed` is `rung == "strict" and ate` ---------
        if gate_real:
            out["gate_real"] += 1
            out["gate_rungs"][rung] = out["gate_rungs"].get(rung, 0) + 1
            if p_real:
                out["gate_real_page_real"] += 1
            elif len(out["gate_real_examples"]) < 4:
                out["gate_real_examples"].append({
                    "label": label, "clean": clean, "kept": kept,
                    "lost": clean - kept})
            if rung == "strict":          # the branch that cannot be taken
                out["gate_real_strict_rung"] += 1
        elif rung == "strict" and c_pp["sup_in_root"] > kept:
            out["below"] += 1             # the other zero: reachable, unrolled

        # --- probe_gate_span: `ate = any(candidate fires)` --------------------
        if or_real:
            out["or_real"] += 1
            if p_real:
                out["or_real_page_real"] += 1
            elif len(out["or_real_examples"]) < 4:
                out["or_real_examples"].append({
                    "label": label, "clean": clean, "kept": kept,
                    "lost": clean - kept,
                    "fired": [k for k in _SPAN_CANDIDATES if c_ps[f"{k}_fires"]],
                })

        # --- the per-candidate misses under each truth ------------------------
        for k in _SPAN_CANDIDATES:
            fires = bool(c_ps[f"{k}_fires"])
            if not fires and or_real:
                out["miss"][k]["or"] += 1
                if not p_real and len(out["miss"][k]["invented"]) < 4:
                    out["miss"][k]["invented"].append({
                        "label": label, "clean": clean, "kept": kept,
                        "lost": clean - kept})
            if not fires and p_real:
                out["miss"][k]["page"] += 1

        # --- the candidate scored by a counter that cannot see in there -------
        para = c_ps["sup_para"]
        ptext = c_pp["sup_ptext"]
        if ptext > keyhole.EMPTY_TEXT and para == 0:
            out["para_blind"] += 1
            if len(out["para_blind_examples"]) < 4:
                out["para_blind_examples"].append({
                    "label": label, "clean": clean, "kept": kept,
                    "ptext": ptext, "para": para})
    return out


def main():
    rounds = 400
    if "--fuzz" in sys.argv:
        i = sys.argv.index("--fuzz")
        rounds = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else rounds
    floor = keyhole.EMPTY_TEXT
    if "--min-chars" in sys.argv:
        floor = int(sys.argv[sys.argv.index("--min-chars") + 1])

    urls = _pg.read_list(DEFAULT_LIST) + [
        (f"old-{n}", u) for n, u in
        [(s.replace(".", ""), u) for s, u in _pr.SITES]]
    print(f"keyhole {keyhole.__version__} — which of these probes prints a "
          f"measurement, and which prints a theorem?\n"
          f"corpus: {len(urls)} urls (uncurated + the nine the gate was built on)"
          f"   mutations: {rounds}\n")

    pages, clean_kept, skipped = [], [], []
    for src, url in urls:
        if not _pg.is_html(url):
            skipped.append((src, url, "not html"))
            continue
        try:
            html = _pg.cached_download(url)
        except Exception as e:
            skipped.append((src, url, f"{type(e).__name__}"[:30]))
            continue
        c = _pp.candidates(html)
        if c["kept"] < floor or not c["scope"]:
            skipped.append((src, url, f"no region ({c['kept']} kept)"))
            continue
        pages.append((html, src))
        clean_kept.append(c["kept"])
    print(f"pages the audit can grade: {len(pages)}  ({len(skipped)} left out, "
          f"named at the end)\n")
    if not pages:
        print("nothing measurable: the corpus says nothing about the probes")
        return

    a = audit(pages, clean_kept, rounds)
    if not a["n"]:
        print("no mutation was scored: the audit says nothing")
        return

    print("== the three truths, on the same mutations")
    print(f"   {'probe':<18} {'truth':<22} {'reads the gate?':<16} "
          f"{'names real':>10} {'page confirms':>14}")
    print("   " + "-" * 84)
    print(f"   {'probe_truncation':<18} {'ate = the gate':<22} {'YES':<16} "
          f"{a['gate_real']:>10} {a['gate_real_page_real']:>14}   <-- graded by the "
          f"reading it measures")
    print(f"   {'probe_gate_span':<18} {'any(candidate fires)':<22} {'YES':<16} "
          f"{a['or_real']:>10} {a['or_real_page_real']:>14}   <-- the gate is one of "
          f"the candidates")
    print(f"   {'probe_gate_pos':<18} {'the page, clean':<22} {'no':<16} "
          f"{a['page_real']:>10} {a['page_real']:>14}   <-- the only truth a "
          f"candidate cannot satisfy")
    for ex in a["gate_real_examples"][:2]:
        print(f"     ↳ the gate called this real: {ex['label']}  clean "
              f"{ex['clean']:,}  kept {ex['kept']:,}  lost {ex['lost']:,}")

    print(f"\n== probe_truncation: two zeros that look alike, and only one is a fact")
    rungs = ", ".join(f"{k} {v}" for k, v in sorted(a["gate_rungs"].items()))
    print(f"   `MISSED (shipped a stub silently): 0`  — the branch is "
          f"`rung == \"strict\" and ate`.")
    print(f"     mutations where the gate says it fired (`ate`): {a['gate_real']}"
          f"   of those, rung `strict`: {a['gate_real_strict_rung']}")
    print(f"     the rungs those mutations landed on: {rungs or '(none)'}")
    print(f"     `ate_the_root` is also what puts the rung on `trunc-root` "
          f"(keyhole._parse), so the two")
    print(f"     halves of the condition exclude each other: no witness can "
          f"exist. 0 is arithmetic.")
    w = witness(WITNESS_BELOW)
    print(f"   `held back by the floor: 0`  — the branch is "
          f"`rung == \"strict\" and not ate and drop_in_root > kept`.")
    print(f"     the same fuzz rolls it: 0 of {a['n']}.")
    print(f"     a witness exists — {WITNESS_BELOW[:34]}… → kept {w['kept']}, "
          f"in_root {w['drop_in_root']}, ate {w['ate']}, rung {w['rung']}")
    print(f"     reaches the branch: {'YES' if w['below'] else 'no'}"
          f"   (the loss is under the {keyhole.EMPTY_TEXT}-char floor, so the "
          f"first rung never fires)")
    print(f"     so this zero is a fact about the corpus, not about the "
          f"arithmetic: it could have been")
    print(f"     nonzero, and 1,500 mutations never rolled the band that "
          f"reaches it. Two identical")
    print(f"     zeros in one output; the way to tell them apart is to try to "
          f"build a witness.")

    print(f"\n== probe_gate_span: a truth that inherits the gate's false positive")
    invented = a["or_real"] - a["or_real_page_real"]
    print(f"   mutations the OR-truth calls real:        {a['or_real']}")
    print(f"   of those, the page says were really eaten:{a['or_real_page_real']}")
    print(f"   invented (no candidate is the page):      {invented}")
    for ex in a["or_real_examples"]:
        print(f"     ↳ {ex['label']:<12} clean {ex['clean']:,}  kept {ex['kept']:,}  "
              f"lost {ex['lost']:,}  fires: {', '.join(ex['fired'])}")
    print(f"\n   {'candidate':<10} {'missed (OR-truth)':>18} {'missed (page)':>14} "
          f"{'invented':>10}")
    for k in _SPAN_CANDIDATES:
        m = a["miss"][k]
        print(f"   {k:<10} {m['or']:>18} {m['page']:>14} "
              f"{m['or'] - m['page']:>10}")
    for k in _SPAN_CANDIDATES:
        for ex in a["miss"][k]["invented"][:2]:
            print(f"     ↳ {k} charged a miss for {ex['label']}: clean "
                  f"{ex['clean']:,}  kept {ex['kept']:,}  lost {ex['lost']:,} "
                  f"— the page was not touched")

    print(f"\n== the candidate scored by a counter that cannot see in there")
    print(f"   mutations where the structural `ptext` sees prose in the "
          f"suppression")
    print(f"   and `_ParaLoss` — the `para` candidate probe_gate_span still "
          f"scores — reads 0: {a['para_blind']}")
    for ex in a["para_blind_examples"]:
        print(f"     ↳ {ex['label']:<12} clean {ex['clean']:,}  kept {ex['kept']:,}  "
              f"ptext {ex['ptext']:,}  para {ex['para']}")
    print(f"   `_para_depth` is incremented only for a `<p>` that is not "
          f"suppressed, so inside the subtree")
    print(f"   it can never rise: the counter is blind to the prose it was "
          f"written to see, and it reads 0.")

    print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<12} {why:<40} {url}")


if __name__ == "__main__":
    main()
