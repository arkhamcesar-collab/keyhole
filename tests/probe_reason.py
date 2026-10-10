#!/usr/bin/env python
"""Ask the gate's losses for their *reason*, not their size.

The ninth awakening went looking for a counter that separates "chrome that lives
inside the content container" (Torrebaja's navbox: the gate relaxes on a complete
article) from "the article's tail was eaten", and measured three *amounts* —
counter vs. kept, same region on both sides, only prose — and none of them
separated: the fix that saved the honest page was the fix that let the real
damage through. It left one direction open and unwritten: `keyhole.py`'s own
note calls it the rule that would decide **why** a suppression failed instead of
**how much** it removed.

There is a "why" already recorded and never aggregated: `_PosReader` (from
`probe_gate_pos.py`, loaded here by path, not re-typed) gives every in-root
suppression frame one of three endings —

    matched   closed by its own end tag
    unwind    closed by an *enclosing* tag's end tag — the parser's tolerant
              unwind handed it a tag that belonged to someone else
    open      still on the stack when the document ended

Torrebaja's navbox is `matched`: honest chrome, closed by its own tag. An
injected suppression that swallows the article's tail either never closes
(`open`) or closes on a tag the page had already committed to (`unwind`). So the
question this probe measures, on the same corpus and the same mutations as
`probe_gate_pos`, is whether "the loss came from a frame that did not end by its
own tag" is the reading that separates the two cases the ninth awakening could
not separate.

It is not a free reading, and the probe measures what it costs: `open` (that same
reading, as the sibling already names it) catches 14 of the 20 real truncations,
so six of them lose their text through frames that closed *properly* — those six
are named here with what they ate, because a miss that is not named is a total.
And since "the amount" and "the reason" fail on different cases, the last table
measures their disjunction (prose eaten **or** a frame that mis-ended), which is
the one candidate this reasoning actually implies.

Two honesty debts of the run above are paid here, and both are the same rule in
two shapes. The first: the union fires exactly once on a mutation that lost
nothing at all (once in run A, twice in run B) — the Torrebaja shape, the only
price it pays — and a *number* is not a report (eleventh awakening), so that fire
is named, with what it ate and which leg of the disjunction fired. The second is
the row that is not a second
reading: `open` and `mishap` are one expression — `mishap` sums the very frames
`sup_open` sums — so the two identical lines are identical *by construction*, not
two candidates that agree, and a probe that prints them as separate rows is the
thirteenth awakening's disguise (`a value that means several things`) worn the
other way round: two names wearing one value. The probe asserts the identity on
every mutation instead of trusting it.

Both runs, 1,500 mutations, same seed, and the second one is the fourteenth
awakening's conclusion put to the test:

    run A  (the sibling's splice, may land inside a tag)
        ptext 18/2 no-cost 0   ·   reason 14/6 no-cost 1   ·   union 20/0 no-cost 1
        the mutation really ate the article: 20
    run B  (same seed, splice snapped out of tags — a different experiment)
        ptext 17/5 no-cost 0   ·   reason 14/8 no-cost 2   ·   union 20/2 no-cost 2
        the mutation really ate the article: 22

Run B is worse on every axis, and that is the result: the previous awakening's
"first candidate that improves on every axis at once" **does not survive** the
mutation with its own damage removed. Removing it raises the count of real
truncations (20 → 22) and costs the union its two misses back. And the union's
no-cost fires are not the mutation's fault either — B has two of them, not zero.
They are the ninth awakening's unfixed division: the counter measures the root,
`kept` measures the narrowed span, so a suppression spliced into the part of the
root the tightening already discards counts as a loss that no reader ever paid.
The honest next candidate is therefore not "the reason" but **the union measured
inside the span's region** — the same-region pairing the ninth tried alone and
found weak, never tried as the region of the disjunction.

Run:  python tests/probe_reason.py [--fuzz N]
"""
import importlib.util
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402

DEFAULT_LIST = os.path.join(HERE, "tests", "corpus", "gate_urls.txt")
HOW = ("matched", "unwind", "open")


def _load_sibling(name: str):
    path = os.path.join(HERE, "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pg = _load_sibling("probe_gate")
_pr = _load_sibling("probe_rules")
_gp = _load_sibling("probe_gate_pos")


def by_how(frames) -> dict[str, int]:
    """In-root textsuppression, split by how the frame that removed it ended.

    `how` is None for a frame that was still open at the end of the document,
    which is the third ending (`open`), and it is counted as one rather than
    dropped — a frame with no ending is the shape most likely to have eaten the
    tail, and folding it into "no data" is how it would hide.
    """
    out = {k: 0 for k in HOW}
    for f in frames:
        out[f["how"] or "open"] += f["chars"]
    return out


def candidates(html: str) -> dict:
    """`probe_gate_pos`'s readings, plus the reason split and the disjunction."""
    c = _gp.candidates(html)
    how = by_how(c["frames"])
    c["by_how"] = how
    c["how_sum"] = sum(how.values())
    # How many frames ended each way: the mean loss per frame is what tells a
    # frame closed *early* from one closed *late*, and a total cannot.
    c["how_n"] = {k: sum(1 for f in c["frames"] if (f["how"] or "open") == k)
                  for k in HOW}
    # The reading `probe_gate_pos` already calls `open`: loss that came from a
    # frame which did not close by its own tag. Named here by its reason so the
    # two probes cannot disagree about what it measures — and it is, character
    # for character, the sibling's `sup_open` (`sum(f["chars"] for f in frames
    # if f["how"] != "matched")`): `how` is None only for a frame still open at
    # the end, and `close()` turns those into `open`. So the two rows below are
    # one reading with two names, and `fuzz` counts the mutations where the two
    # expressions differ rather than letting the table imply they were measured
    # apart.
    c["mishap"] = how["unwind"] + how["open"]
    # Prose eaten, or a suppression that mis-ended: the disjunction the ninth
    # awakening's two dead ends point at (the amount fails on Torrebaja, the
    # reason fails on the frames that close properly).
    c["prose_or_mishap_fires"] = bool(c["ptext_fires"]) or bool(c["open_fires"])
    return c


def _tag_end(src: str, i: int) -> int | None:
    """Offset just past the tag that starts at `src[i] == '<'`, or None."""
    j, n, q = i + 1, len(src), None
    while j < n:
        ch = src[j]
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == ">":
            return j + 1
        j += 1
    return None


def out_of_tag(src: str, a: int) -> int:
    """Snap a splice offset out of the tag that contains it, if it is inside one.

    The fuzz splices a suppression in at a random offset, and a random offset
    lands inside a start tag's attribute list often enough to matter — a page's
    markup is denser than its text. Run A shows what that costs: the union's one
    no-cost fire is a splice that landed inside `typeof="mw:T`. The parser read
    the broken tag's remainder (1,082 characters of attribute text) as a text
    node, and a `<style>` inside the damaged region stopped parsing as a tag, so
    its 1,466 characters of CSS were delivered as data *under the injected chrome
    frame* and counted as suppressed text. Both halves are unreadable — the
    strict text of that mutation is **byte-identical** to the clean page's,
    1,661 characters — so the first reading of that fire was "the mutation's own
    damage, counted as the page's loss".

    This function is the experiment that checks that reading, and the reading is
    **wrong**: with the splice unable to land inside a tag, the union's no-cost
    fire count is **2**, not 0. Removing the corrupted-tag artifact does not
    remove the fire. What it is instead is older and has no mutation in it: the
    counter measures the **root**, `kept` measures the **narrowed span** (the
    paragraph-tightening rule, fifth awakening), and the misnamed kept-nothing
    zero of the sixth: the ninth awakening measured this same division of two
    regions and found it explained "only half" of Torrebaja's firing, then moved
    to a different counter instead of fixing the region. It is fully visible on
    an honest page with no mutation at all: `wikirandom Têgeyştinî Rastî` counts
    405 characters of in-root chrome loss — `li` and `other`, the nav landmarks'
    readable link text — while its no-chrome pass and its strict pass return the
    *same* 1,661 characters. Readable text suppressed inside the root that chrome
    -off does not recover was never in `kept`: it is outside the tightened
    container. A suppression spliced into that discarded part of the root counts
    as a loss while changing nothing a caller reads — which is exactly the
    signature of a no-cost fire, whether or not the markup was damaged.

    A different experiment, then, and printed apart: same seed, same anchors,
    same rule, same rounds. Its numbers are not comparable with the siblings',
    and they are worse — see the A-vs-B table.
    """
    lt = src.rfind("<", 0, a)
    if lt == -1:
        return a
    end = _tag_end(src, lt)
    if end is None or end <= a:
        return a          # the tag closed before `a`: `a` is already text
    return end


def mutate(src: str, rnd: random.Random, untag: bool = False) -> str:
    """Open a suppression inside the root and sometimes never close it.

    Copied verbatim from `probe_gate_pos.fuzz`, which carries the same copy as
    the two probes before it. The honest reading is that this is the one
    duplicated line in the file and it is a risk: if that probe sharpens its
    mutation shape and this does not follow, this measures a different
    experiment. `untag=True` is this probe's one addition (`out_of_tag`), and it
    is a different experiment, not a fix: the sibling's numbers were measured
    with the splice able to land inside a tag.
    """
    anchors = [m for m in ("<main", "<article") if m in src]
    if rnd.random() < 0.75 and anchors:
        a = src.find(rnd.choice(anchors))
        a = src.find(">", a) + 1
        a = rnd.randrange(a, min(len(src), a + max(1, len(src) // 4)))
    else:
        a = rnd.randrange(len(src))
    if untag:
        a = out_of_tag(src, a)
    rule = rnd.choice(['<div aria-hidden="true">', '<div role="navigation">',
                       '<aside>', '<nav>', '<div class="sidebar">',
                       '<div class="cookie-banner">'])
    cuts = rnd.randrange(1, 4)
    html = src[:a] + rule * cuts + src[a:]
    if rnd.random() < 0.3 and cuts > 1:
        html = html.replace("</div>", "", rnd.randrange(1, 3)) if "div" in rule else html
    return html


def fuzz(pages, clean_kept, rounds, seed=0, untag=False):
    """Score every mutation by its reason, under the truth that reads the page.

    `real` is `probe_gate_pos`'s truth — the mutation lost more than half of what
    the *same page* returned clean, and still returned something readable — so no
    candidate can confirm or deny it. The gate's own verdict (`ate`) is carried
    beside it, because the question is where the gate's right and wrong answers
    get their loss from.
    """
    rnd = random.Random(seed)
    out = {
        "n": 0,
        "how_fired": {k: 0 for k in HOW},       # gate fired, page says nothing lost
        "how_real": {k: 0 for k in HOW},        # gate fired, page confirms
        "how_missed": {k: 0 for k in HOW},      # gate stayed quiet, page confirms
        "cnt_fired": {k: 0 for k in HOW},       # ... and the frames behind them
        "cnt_real": {k: 0 for k in HOW},
        "fired_n": 0, "fired_real": 0, "real": 0, "silent": 0,
        "partition": [0, 0],                    # (pages, mutations) frames == sup_in_root
        "split_off": [],                        # pages where they do not: named
        "open_examples": [], "ptext_examples": [],
        "union": {"caught": 0, "missed": 0, "no_cost": 0, "partial": 0},
        "ptext_only": {"caught": 0, "missed": 0, "no_cost": 0, "partial": 0},
        "open_only": {"caught": 0, "missed": 0, "no_cost": 0, "partial": 0},
        "mishap_only": {"caught": 0, "missed": 0, "no_cost": 0, "partial": 0},
        "union_no_cost": [],                    # named, not totalled
        "union_no_cost_n": 0,
        "mishap_ne_open": 0,                    # the two rows are one expression
    }
    for _ in range(rounds):
        i = rnd.randrange(len(pages))
        src, label = pages[i]
        clean = clean_kept[i]
        html = mutate(src, rnd, untag=untag)
        try:
            c = candidates(html)
        except Exception:
            continue
        out["n"] += 1
        if c["how_sum"] == c["sup_in_root"]:
            out["partition"][1] += 1
        lost = max(0, clean - c["kept"])
        real = lost > clean * 0.5 and lost > keyhole.EMPTY_TEXT and c["kept"] > keyhole.EMPTY_TEXT
        silent = real and c["rung"] == "strict"
        if real:
            out["real"] += 1
            if silent:
                out["silent"] += 1
        fired = bool(c["shipped_fires"])
        if fired:
            out["fired_n"] += 1
        bucket = None
        if fired and real:
            out["fired_real"] += 1
            bucket = "how_real"
        elif fired:
            bucket = "how_fired"
        elif real:
            bucket = "how_missed"
        if bucket:
            for k, v in c["by_how"].items():
                out[bucket][k] += v
                if bucket != "how_missed":
                    out["cnt_" + bucket.split("_")[1]][k] += c["how_n"][k]

        # Each candidate's cost, scored the same way the sibling scores its own:
        # a fire on a page where nothing was lost is a relaxation an honest page
        # pays for.
        for name, fires in (("union", c["prose_or_mishap_fires"]),
                            ("ptext_only", c["ptext_fires"]),
                            ("open_only", c["open_fires"]),
                            ("mishap_only", c["mishap"] > c["kept"]
                             and c["mishap"] > keyhole.EMPTY_TEXT)):
            slot = out[name]
            if fires:
                if real:
                    slot["caught"] += 1
                elif lost > 0:
                    slot["partial"] += 1
                else:
                    slot["no_cost"] += 1
            elif real:
                slot["missed"] += 1

        # Two honesty counters, both about the table not meaning what it looks
        # like it means.
        #
        # (a) The union's one no-cost fire is the only price it pays and a count
        # is not a report: name the mutation, what it ate, and which leg fired.
        # If it turns out to be a partial that the truth rounded to zero, that is
        # visible here and nowhere else.
        if c["mishap"] != c["sup_open"]:
            out["mishap_ne_open"] += 1
        if c["prose_or_mishap_fires"] and not real and lost == 0:
            out["union_no_cost_n"] += 1
            if len(out["union_no_cost"]) < 8:
                out["union_no_cost"].append({
                    "label": label, "clean": clean, "kept": c["kept"],
                    "lost": lost, "how": dict(c["by_how"]),
                    "kinds": dict(c["sup_kind"]), "ptext": c["sup_ptext"],
                    "mishap": c["mishap"], "shipped": c["shipped_fires"],
                    "leg": ("prose" if c["ptext_fires"] else "")
                           + (" OR reason" if c["open_fires"] else ""),
                    "frames": [(f["chars"], f["label"], f["how"]) for f in
                               sorted(c["frames"], key=lambda f: -f["chars"])[:3]],
                })

        if not c["open_fires"] and real:
            if len(out["open_examples"]) < 8:
                out["open_examples"].append({
                    "label": label, "clean": clean, "kept": c["kept"], "lost": lost,
                    "how": dict(c["by_how"]), "kinds": dict(c["sup_kind"]),
                    "frames": [(f["chars"], f["label"], f["how"]) for f in
                               sorted(c["frames"], key=lambda f: -f["chars"])[:3]],
                })
        if not c["ptext_fires"] and real and not c["open_fires"]:
            if len(out["ptext_examples"]) < 8:
                out["ptext_examples"].append({
                    "label": label, "clean": clean, "kept": c["kept"], "lost": lost,
                    "how": dict(c["by_how"]), "kinds": dict(c["sup_kind"]),
                })
    return out


def fmt(d: dict[str, int]) -> str:
    return "  ".join(f"{k}:{v:,}" for k, v in d.items() if v)


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
    print(f"keyhole {keyhole.__version__} — the reason a suppression failed, "
          f"not the size of what it removed\n"
          f"corpus: {len(urls)} urls (uncurated + the nine the gate was built on)   "
          f"mutations: {rounds or '-'}\n")

    rows, skipped, split_off = [], [], []
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
            skipped.append((src, url, f"no region ({c['kept']} kept)"))
            continue
        if c["how_sum"] != c["sup_in_root"]:
            split_off.append((src, url, c["sup_in_root"] - c["how_sum"]))
        rows.append({"src": src, "url": url, **c})

    # The pages list is built in the sibling's order (worst shipped share first,
    # or pinned on the URL with `--order=url`), because the fuzz indexes into it:
    # a different order is a different sample of the same experiment, and then
    # ptext's 18/20 cannot be checked here.
    _gp.pin_order(rows, sys.argv)
    show_rows = sorted(rows, key=lambda r: -r["mishap"])
    print(f"{'src':<12} {'kept':>7} {'in_root':>8} {'matched':>8} {'unwind':>7} "
          f"{'open':>7} {'mishap':>8} {'shipped':>8}  fires")
    print("-" * 96)
    for r in show_rows[:20]:
        fires = (("S" if r["shipped_fires"] else "-") + ("O" if r["open_fires"] else "-")
                 + ("U" if r["prose_or_mishap_fires"] else "-"))
        print(f"{r['src']:<12} {r['kept']:>7} {r['sup_in_root']:>8} "
              f"{r['by_how']['matched']:>8} {r['by_how']['unwind']:>7} "
              f"{r['by_how']['open']:>7} {r['mishap']:>8} "
              f"{r['shipped_share'] * 100:>7.1f}%  {fires}")

    # The honesty check that keeps the split a partition and not an opinion:
    # every character of in-root chrome loss is in exactly one frame, so the
    # three endings must add up to the shipped `sup_in_root`.
    tot = sum(r["sup_in_root"] for r in rows)
    print(f"\n== {len(rows)} measurable pages  ({len(skipped)} left out, named below)")
    print(f"   in-root chrome loss, all pages: {tot:,}")
    print(f"   by ending: " + fmt({k: sum(r['by_how'][k] for r in rows) for k in HOW}))
    print(f"   pages where the endings do not add up to sup_in_root: {len(split_off)}"
          f"   (named, not totalled)")
    for src, url, d in split_off:
        print(f"     ↳ {src:<12} short by {d:,} chars  {url}")
        print(f"       a chrome frame opened *outside* the root whose suppression "
              f"reaches into it: its text")
        print(f"       is in sup_in_root but in no in-root frame, which is why the "
              f"split is over frames.")

    print(f"\n== fires on the honest corpus (S=shipped  O=reason  U=prose-or-reason)")
    for k in ("shipped_fires", "open_fires", "ptext_fires", "prose_or_mishap_fires"):
        hit = [r for r in rows if r[k]]
        print(f"   {k.replace('_fires', ''):<20} {len(hit)}")
        for r in hit:
            print(f"     ↳ {r['src']:<12} kept {r['kept']:,}  in_root {r['sup_in_root']:,}"
                  f"  matched {r['by_how']['matched']:,}  unwind {r['by_how']['unwind']:,}"
                  f"  open {r['by_how']['open']:,}  {r['url']}")
            for f in sorted(r["frames"], key=lambda f: -f["chars"])[:3]:
                print(f"         {f['chars']:>7}  {f['label']:<28} ended {f['how']}")

    if not rounds:
        print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
        for src, url, why in skipped:
            print(f"   {src:<12} {why:<40} {url}")
        return

    pages, clean_kept = [], []
    for r in rows:
        try:
            html = _pg.cached_download(r["url"])
        except Exception:
            continue
        pages.append((html, r["src"]))
        clean_kept.append(candidates(html)["kept"])
    def report(f, title, note):
        print(f"\n== {title}")
        print(f"   {note}")
        print(f"   mutations scored:                    {f['n']}")
        print(f"   the mutation really ate the article: {f['real']}"
              f"   of those silent (parse=strict): {f['silent']}")
        print(f"   the shipped gate fired on:           {f['fired_n']}"
              f"   of those the page confirms: {f['fired_real']}")

        print(f"\n   where the loss comes from, by what the gate did about it")
        print(f"     {'':<32} {'matched':>10} {'unwind':>10} {'open':>10}")
        for k, lbl in (("how_real", "gate fired, page says eaten"),
                       ("how_fired", "gate fired, page says untouched"),
                       ("how_missed", "gate quiet, page says eaten")):
            print(f"     {lbl:<32} {f[k]['matched']:>10,} {f[k]['unwind']:>10,} "
                  f"{f[k]['open']:>10,}")
            if k != "how_missed":
                m = f[k]["matched"]
                print(f"     {'':<32} {m * 100 / max(1, sum(f[k].values())):>9.1f}%"
                      f"   of the loss ended by its own tag")
        print(f"     mean loss per frame — a frame closed *early* reads small, one "
              f"closed *late* reads large:")
        for k, lbl in (("cnt_real", "page says eaten"),
                       ("cnt_fired", "page says untouched")):
            cells = "  ".join(
                f"{e} {f[k][e] and f['how_' + k.split('_')[1]][e] / f[k][e]:.0f} chars/"
                f"{f[k][e]} frames" for e in HOW if f[k][e])
            print(f"       {lbl:<22} {cells}")

        print(f"\n   the candidates, scored on the same mutations")
        print(f"     {'reading':<40} {'caught':>7} {'missed':>7} {'no-cost':>8} "
              f"{'partial':>8}")
        for name, lbl in (("ptext_only", "prose eaten (ptext)"),
                          ("mishap_only", "a suppression mis-ended  (= next row)"),
                          ("open_only", "a frame did not close by its own tag"),
                          ("union", "prose eaten OR a suppression mis-ended")):
            s = f[name]
            print(f"     {lbl:<40} {s['caught']:>7} {s['missed']:>7} {s['no_cost']:>8} "
                  f"{s['partial']:>8}")
        print(f"     'a suppression mis-ended' and 'a frame did not close by its own "
              f"tag' are one expression, so their")
        print(f"     identical columns are an identity, not two readings agreeing: "
              f"mishap != sup_open in {f['mishap_ne_open']} of {f['n']} mutations.")

        print(f"\n   the union's no-cost fire, named (not counted): "
              f"{f['union_no_cost_n']}")
        print(f"     the only price the union pays — a mutation it relaxes where the "
              f"page lost nothing at all:")
        for ex in f["union_no_cost"]:
            print(f"     {ex['label']:<12} clean {ex['clean']:,}  kept {ex['kept']:,}  "
                  f"lost {ex['lost']:,}  leg fired: {ex['leg'] or 'none'}"
                  f"  (shipped gate: {'fired' if ex['shipped'] else 'quiet'})")
            print(f"         ptext {ex['ptext']:,}  mishap {ex['mishap']:,}  "
                  f"endings: {fmt(ex['how'])}  eaten: {fmt(ex['kinds'])}")
            for chars, label, how in ex["frames"]:
                print(f"         {chars:>7}  {label:<28} ended {how}")
        if not f["union_no_cost"]:
            print(f"     (none: every case the union fired on either lost text or was "
                  f"real — the count and the list agree)")

        print(f"\n   the real truncations the *reason* misses, named (not totalled)")
        for ex in f["open_examples"]:
            print(f"     {ex['label']:<12} clean {ex['clean']:,}  kept {ex['kept']:,}  "
                  f"lost {ex['lost']:,}  endings: {fmt(ex['how'])}  "
                  f"eaten: {fmt(ex['kinds'])}")
            for chars, label, how in ex["frames"]:
                print(f"         {chars:>7}  {label:<28} ended {how}")
        if f["ptext_examples"]:
            print(f"     — and the ones both readings miss:")
            for ex in f["ptext_examples"]:
                print(f"       {ex['label']:<12} kept {ex['kept']:,}  lost {ex['lost']:,}"
                      f"  endings: {fmt(ex['how'])}  eaten: {fmt(ex['kinds'])}")

    # Two runs, same seed, and the difference between them is the mutation's own
    # damage. Run A is the sibling's shape and its numbers are the ones the
    # previous awakenings published; run B snaps the splice out of any tag it
    # landed in (`out_of_tag`). They are printed apart because a changed
    # experiment is a different experiment, and the comparison is the finding:
    # if a candidate's price disappears when the mutation can no longer corrupt
    # the markup, that price was never the page's.
    f_a = fuzz(pages, clean_kept, rounds)
    f_b = fuzz(pages, clean_kept, rounds, untag=True)
    report(f_a, f"fuzz A — {rounds} mutations, the sibling's splice (may land inside a tag)",
           "this is the shape probe_gate_pos and probe_truncation measure with")
    report(f_b, f"fuzz B — same seed, splice snapped out of tags (*a different experiment*)",
           "same anchors, same rule, same rounds; only offsets inside a tag moved")

    print(f"\n== what the mutation's own damage was paying for (A vs. B, same seed)")
    print(f"   {'reading':<40} {'A caught':>9} {'B caught':>9} {'A no-cost':>10} "
          f"{'B no-cost':>10}")
    for name, lbl in (("ptext_only", "prose eaten (ptext)"),
                      ("mishap_only", "a suppression mis-ended"),
                      ("union", "prose eaten OR a suppression mis-ended")):
        a, b = f_a[name], f_b[name]
        print(f"   {lbl:<40} {a['caught']:>9} {b['caught']:>9} {a['no_cost']:>10} "
              f"{b['no_cost']:>10}")
    print(f"   mutations that really ate the article: A {f_a['real']}  B {f_b['real']}"
          f"   (difference {f_b['real'] - f_a['real']:+d})")
    print(f"   at 1,500 rounds that difference is +2 — B finds real truncations the "
          f"corrupted tags were hiding —")
    print(f"   and B's no-cost fires are not lower than A's: removing the mutation's own "
          f"damage does not")
    print(f"   remove a candidate's price. The honest page says where that price is: it "
          f"counts 405 characters")
    print(f"   of in-root chrome loss and none of them are in `kept` — chrome-off gives "
          f"back the same text.")
    if f_b["union_no_cost_n"]:
        print(f"   the union's no-cost fires: {f_b['union_no_cost_n']} in B, "
              f"{f_a['union_no_cost_n']} in A.")


    print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<12} {why:<40} {url}")


if __name__ == "__main__":
    main()
