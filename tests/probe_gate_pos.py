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

Twenty-third awakening — the prose row's own two halves. The twenty-second found
that the prose row of `probe_gate_span` (`_ParaLoss`) was not blind but *looking
the other way*: it counted only a `<p>` opened before the suppression and still
open across it, so it saw inline chrome and missed the block chrome that ate whole
paragraphs. The fix made that row count a `<p>` opened on *either* side, and the
union is a strict superset of this probe's `ptext` (6,319 vs 5,566 characters on
the honest corpus). The open question it left is whether *this* probe should read
the union too, and the reading that is a matter of measurement rather than taste is

    punion  the same structural reading, plus everything a `<p>` opened *outside*
            the frame removed: the union, as a row in the fuzz that grades
            against the page

with the 753 characters it adds **named** rather than counted, and the union
cross-checked page by page against the span family's own `_ParaLoss` (0
disagreements expected; a probe that quietly disagrees with its sibling is the
second-costume sin, not a second opinion).

Run:  python tests/probe_gate_pos.py [--fuzz N] [--min-chars N] [--order=url]

`--order=url` pins the page order on the URL instead of on `shipped_share`, so
the fuzz's sample is shared between an A and a B of the counter; the printed
sample digest is the witness (see `pin_order`).
"""
import hashlib
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

CANDIDATES = ("shipped", "span", "ptext", "open", "ppara", "plist", "punion")

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
_ps = _load_sibling("probe_gate_span")


def _fmt_kinds(kinds) -> str:
    """The breakdown in one cell, biggest first, empty kinds left out."""
    if not kinds:
        return "-"
    return " ".join(f"{k}:{v}" for k, v in
                    sorted(kinds.items(), key=lambda kv: -kv[1]) if v)


def _by_how(frames) -> dict:
    """A frame ledger — ``matched`` / ``unwind`` / ``open`` — summed by chars.

    The twenty-ninth awakening read this census on the *honest* side (the pages
    the gate relaxes on with nothing done to them): 208,626 characters, every one
    of them removed by a frame that closed with its own end tag, ``unwind`` 0 and
    ``open`` 0. That is half a statement, because the shape this gate exists to
    catch — the suppression that never closed and ate the article's tail — is a
    claim about *mutations*, and mutations are not in a census of pages nothing
    happened to. This function is the same ledger, moved to the other side.
    """
    out: dict = {}
    for f in frames:
        out[f["how"]] = out.get(f["how"], 0) + f["chars"]
    return out


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
      * `sup_pinline` — the other half of the same criterion. The prose row in
        `probe_gate_span` (`_ParaLoss`) now counts a `<p>` opened on *either*
        side of the suppression, and that union is a strict superset of
        `sup_ptext`: 6,319 vs 5,566 characters on the honest corpus, and the 753
        it adds are counted where a `<p>` was already open *outside* the frame.
        This counter measures that half separately instead of assuming it is
        prose — and names it (`inline_samples`).
    """

    def __init__(self, scope: bool = True):
        super().__init__(scope)
        self.sup_ptext = 0
        self.sup_pinline = 0
        self.inline_samples: list[tuple[str, str]] = []
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
                if self._para_depth:
                    # The union's extra half: a paragraph that was opened
                    # *before* the frame and is still open through it. Whether
                    # that is prose is not a matter of taste — it is a question
                    # about what the frame actually removed, so the counter
                    # keeps the text and the frame it came from.
                    self.sup_pinline += len(data)
                    if len(self.inline_samples) < 6:
                        lab = next((f["label"] for f in reversed(self.frames)
                                    if f["how"] is None), "?")
                        self.inline_samples.append(
                            (lab, " ".join(data.split())[:60]))
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
    punion = ptext + pos.sup_pinline
    li = pos.sup_kind.get("li", 0)
    plist = ptext + li
    open_ = sum(f["chars"] for f in pos.frames if f["how"] != "matched")
    return {
        "kept": kept,
        "kept_nc": kept_nc,
        "kept_para": pos._para,
        "sup_in_root": m["drop_in_root"],
        "sup_ptext": ptext,
        "sup_pinline": pos.sup_pinline,
        "sup_punion": punion,
        "inline_samples": pos.inline_samples,
        "sup_li": li,
        "sup_plist": plist,
        "sup_kind": pos.kinds(),
        "sup_open": open_,
        "shipped_share": m["ratio"],
        "shipped_fires": m["ate"],
        "span_share": (lost / kept_nc) if kept_nc else 0.0,
        "span_fires": lost > kept and lost > floor,
        "ptext_fires": ptext > kept and ptext > floor,
        # The twenty-second awakening's row, carried into the fuzz that grades
        # against the page instead of against a candidate: the prose row of
        # `probe_gate_span` counts a `<p>` opened on *either* side of the
        # suppression. Reading the union instead of the structural half is the
        # question, so it is a row and not an opinion.
        "punion_fires": punion > kept and punion > floor,
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
                "real_kinds": {}, "real_kind_chars": {}, "blind": 0,
                "blind_named": [],
                # the damage's own frame ledger, the mirror of the honest census:
                # what the mutated page ate, split by how each frame ended, and
                # the same total on the *clean* page it was cut from — because a
                # Wikipedia page's navbox frame is in both ledgers and a
                # subtraction has to be a measurement, not a subtraction.
                "real_how": {}, "clean_how": {}, "real_top": []})
    clean_c: dict = {}
    clean_counted: set = set()
    for _ in range(rounds):
        i = rnd.randrange(len(pages))
        src, label, url = pages[i]
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
                # Two counters, because the line this feeds said "(chars)" while
                # counting cases: `real_kinds` adds 1 per real truncation that ate
                # this kind, and it has been printed as a character total since
                # the tenth awakening. The count stays where it is (it is what
                # earlier runs printed and a probe that names must not move the
                # measurement); the label gets fixed and the chars get a counter
                # of their own, so the two readings are two.
                out["real_kinds"][k] = out["real_kinds"].get(k, 0) + 1
                out["real_kind_chars"][k] = out["real_kind_chars"].get(k, 0) + v
            # The other half of the twenty-ninth awakening's census, on the side
            # where the damage lives. `src` is the clean page the mutation was cut
            # from, so both ledgers are printed for the *same* page: a Wikipedia
            # navbox frame is in the clean ledger and is still there in the damaged
            # one, and attributing it to the mutation would be the twenty-second
            # awakening's sin — a subtraction claimed instead of shown.
            if i not in clean_c:
                try:
                    clean_c[i] = candidates(src)
                except Exception:
                    clean_c[i] = None
            c_clean = clean_c[i] or {}
            how_m = _by_how(c["frames"])
            how_ck = _by_how(c_clean.get("frames") or [])
            for kk, vv in how_m.items():
                out["real_how"][kk] = out["real_how"].get(kk, 0) + vv
            # The clean ledger is a fact *about a page*, so it enters the total
            # once per page and not once per mutation: a page hit three times in
            # 1,500 rounds would otherwise be counted three times and the
            # comparison with the mutated total would be against a number with a
            # different definition — a total that means something else is the
            # twenty-eighth awakening's sin.
            if i not in clean_counted:
                clean_counted.add(i)
                for kk, vv in how_ck.items():
                    out["clean_how"][kk] = out["clean_how"].get(kk, 0) + vv
            top = max(c["frames"], key=lambda fr: fr["chars"], default=None)
            ctop = max(c_clean.get("frames") or [], key=lambda fr: fr["chars"],
                       default=None)
            if top is not None and len(out["real_top"]) < 10:
                out["real_top"].append({
                    "page": label, "url": url, "clean": clean, "kept": c["kept"],
                    "lost": lost, "label": top["label"], "how": top["how"],
                    "chars": top["chars"], "kinds": dict(top["kinds"]),
                    "in_root": c["sup_in_root"],
                    "clean_in_root": c_clean.get("sup_in_root", 0),
                    "clean_top": (ctop or {}).get("how", "-"),
                    "clean_top_chars": (ctop or {}).get("chars", 0),
                    "scope": c["scope"], "rung": c["rung"],
                })
            if silent:
                out["silent"] += 1
            else:
                out["caught_now"] += 1
            # A real truncation on a page whose *region* is empty. Every reading
            # that attributes the loss to a frame inside the root returns 0 here
            # — not because it is blind, but because its numerator lives in a
            # region that does not exist on this page. The zero is structural,
            # and it is the shape the twenty-fourth awakening went looking for:
            # the family's blind spot is not the counter, it is the region.
            if c["sup_in_root"] == 0 and c["kept_nc"] > c["kept"]:
                out["blind"] += 1
                if len(out["blind_named"]) < 4:
                    out["blind_named"].append((label, url, clean, c["kept"],
                                               c["kept_nc"], c["scope"]))
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
                        "label": label, "url": url, "clean": clean,
                        "kept": c["kept"], "kept_nc": c["kept_nc"],
                        "lost": lost, "kinds": dict(c["sup_kind"]),
                        "ptext": c["sup_ptext"], "li": c["sup_li"],
                        "inline": c["sup_pinline"],
                        "in_root": c["sup_in_root"], "scope": c["scope"],
                        "rung": c["rung"],
                    })
    return out


def pin_order(rows, argv):
    """Sort the pages the fuzz indexes into — and say which sample it is.

    The eighteenth awakening named the trap: a probe that orders its pages by the
    number it measures cannot measure a *before and after* of that number. The
    fuzz picks its page *by index*, so re-sorting the list re-rolls the sample,
    and two runs of the same probe score two different mutation sets — *this vs.
    that*, never *before vs. after*. `--order=url` pins the order on a key the
    counter cannot move, so the same index is the same page in both runs.

    `probe_drop` grew this first; the siblings (this one, `probe_region`,
    `probe_reason`) share the definition here so "pinned" means one thing. The
    digest is the witness: same digest, same mutations, and the only thing that
    changed is the counter under test.
    """
    pinned = "--order=url" in argv
    rows.sort(key=(lambda r: r["url"]) if pinned
              else (lambda r: -r["shipped_share"]))
    seq = "|".join(f"{r['src']}:{r['url']}" for r in rows)
    digest = hashlib.sha256(seq.encode()).hexdigest()[:16]
    print(f"   page order: {len(rows)} pages "
          + ("pinned by url — invariant to the counter under test" if pinned
             else "by shipped_share — the number under test")
          + f"   sample digest {digest}")
    return digest


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
    desync = []
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
        # The union this probe adds must be the *same number* as the prose row of
        # the span family — same criterion, two instruments. If it is not, this
        # probe is measuring something of its own and every comparison with the
        # 22nd awakening's runs is off: the instrument that quietly disagrees with
        # its sibling is the second-costume sin.
        union_row = keyhole._reader(html, _ps._ParaLoss).sup_para
        if union_row != c["sup_punion"]:
            desync.append((src, url, union_row, c["sup_punion"]))
        rows.append({"src": src, "url": url, **c})

    pin_order(rows, sys.argv)
    print(f"{'src':<12} {'kept':>7} {'kc':>7} {'in_root':>8} {'in_ptext':>8} "
          f"{'in_line':>7} {'in_li':>7} {'unclosed':>8} {'shipped':>8} {'region':>8}  fires")
    print("-" * 112)
    for r in rows:
        fires = (("S" if r["shipped_fires"] else "-") + ("R" if r["span_fires"] else "-")
                 + ("P" if r["ptext_fires"] else "-") + ("U" if r["punion_fires"] else "-")
                 + ("O" if r["open_fires"] else "-"))
        print(f"{r['src']:<12} {r['kept']:>7} {r['kept_nc']:>7} {r['sup_in_root']:>8} "
              f"{r['sup_ptext']:>8} {r['sup_pinline']:>7} {r['sup_li']:>7} "
              f"{r['sup_open']:>8} "
              f"{r['shipped_share'] * 100:>7.1f}% {r['span_share'] * 100:>7.1f}%  {fires}")

    print(f"\n== {len(rows)} measurable pages  ({len(skipped)} left out, named below)")
    print(f"   what the removed root text is made of, worst ten pages:")
    for r in rows[:10]:
        print(f"     {r['src']:<12} in_root {r['sup_in_root']:>7}  "
              f"{_fmt_kinds(r['sup_kind'])}")
    inl = [r for r in rows if r["sup_pinline"]]
    tot_inl = sum(r["sup_pinline"] for r in inl)
    tot_uni = sum(r["sup_punion"] for r in rows)
    tot_str = sum(r["sup_ptext"] for r in rows)
    print(f"\n   the prose row's two halves, on the honest corpus:  structural "
          f"{tot_str:,}   inline {tot_inl:,}   union {tot_uni:,}")
    print(f"   — the union's extra is what a <p> opened *outside* the frame "
          f"removed ({tot_inl:,} chars on {len(inl)} pages), and it is named here"
          f" instead of counted:")
    for r in inl:
        for lab, snip in r["inline_samples"][:3]:
            print(f"     {r['src']:<12} {r['sup_pinline']:>5,} in {lab:<26} {snip!r}")
    print(f"   union cross-check against the span family's own _ParaLoss: "
          f"{len(rows)} pages, {len(desync)} disagreements"
          + ("" if not desync else "  <-- DESYNC"))
    for src, url, a, b in desync[:6]:
        print(f"     {src:<12} row {a:,} vs probe {b:,}  {url}")
    for k, lbl in (("shipped_share", "shipped (counter vs kept)"),
                   ("span_share", "same region (both passes)")):
        vals = sorted(r[k] for r in rows if r["kept"] >= floor)
        print(f"   {lbl:<32} max {max(vals) * 100:>5.1f}%  p90 "
              f"{vals[int(len(vals) * .9)] * 100:>5.1f}%  median {statistics.median(vals) * 100:>5.1f}%")
    # The pages where the counter is at zero *by construction*, named. A row
    # whose scope is `empty-root` returns text the root never contained: the
    # numerator of every region reading is inside a region that does not exist,
    # so its 0.0% is not a measurement of that page, it is arithmetic. The
    # honest census comes before the fuzz one on purpose — if the shape is
    # already here without any mutation, the fuzz is not producing it.
    blind = [r for r in rows if r["scope"] == keyhole.SCOPE_EMPTY_ROOT]
    print(f"\n   pages whose region is empty (scope {keyhole.SCOPE_EMPTY_ROOT}): "
          f"{len(blind)} of {len(rows)}"
          + (f"  — {sum(r['shipped_share'] for r in blind) * 100:.1f}% total share"
             f" by construction" if blind else ""))
    for r in blind:
        lost = r["kept_nc"] - r["kept"]
        print(f"     {r['src']:<12} kept {r['kept']:>7,}  no-chrome {r['kept_nc']:>7,}  "
              f"unattributed loss {lost:>6,}  in_root {r['sup_in_root']:,}  {r['url']}")
    print(f"\n   fires on the honest corpus:  "
          + "   ".join(f"{k.replace('_fires', '')} {len([r for r in rows if r[k]])}"
                       for k in ("shipped_fires", "span_fires", "ptext_fires",
                                 "punion_fires", "ppara_fires", "plist_fires",
                                 "open_fires")))
    for k in ("shipped_fires", "span_fires", "ptext_fires", "punion_fires",
              "ppara_fires", "plist_fires", "open_fires"):
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
            # (html, src, url) — the URL rides along so a MISSED case can be
            # *named* instead of described by its corpus: the twenty-fourth
            # awakening could read "hn clean 2 513 kept 314" and had no way to
            # say which page it was, which is the same hole that the eleventh
            # closed by printing the kind breakdown instead of counting cases.
            pages.append((html, r["src"], r["url"]))
            clean_kept.append(candidates(html)["kept"])
        print(f"\n== fuzz: {rounds} mutations that open a suppression inside the root")
        f = fuzz(pages, clean_kept, rounds)
        print(f"   mutations scored:                     {f['n']}")
        print(f"   the mutation really ate the article:  {f['real']}"
              f"   (strict kept > {keyhole.EMPTY_TEXT} chars and lost > half of")
        print(f"     {'':<34}the page's own clean extraction)")
        print(f"     {'':<34}how many of them ate each kind (cases, not chars):"
              f" {_fmt_kinds(f['real_kinds'])}")
        print(f"     {'':<34}how much of each kind (chars):"
              f"  {_fmt_kinds(f['real_kind_chars'])}")
        print(f"     of those, the damaged pages' whole frame ledger, by how:"
              f"  {_fmt_kinds(f['real_how'])}")
        print(f"     the same pages, clean, their own frames by how:"
              f"  {_fmt_kinds(f['clean_how'])}")
        print(f"   of those, the ladder caught it:       {f['caught_now']}")
        print(f"   of those, SILENT (parse=strict):      {f['silent']}   <-- what the gate")
        print(f"     {'':<34}exists to catch")
        print(f"   of those, on a page whose region is empty: {f['blind']}"
              f"   <-- 0 attributed is arithmetic, not agreement")
        for label, url, clean, kept, kept_nc, scope in f["blind_named"]:
            print(f"     {label:<12} {url}\n"
                  f"       clean {clean:,} kept {kept:,} no-chrome {kept_nc:,} "
                  f"scope {scope}  — every frame-attributing row reads 0 here")
        print(f"\n   {'':<8} {'caught':>7} {'missed':>7} {'silent':>8} {'no-cost':>8} {'partial':>8}")
        for k in CANDIDATES:
            print(f"   {k:<8} {f[k]['caught']:>7} {f[k]['missed_real']:>7} "
                  f"{f[k]['silent_caught']:>3}/{f['silent']:<4} {f[k]['zero_cost']:>8} "
                  f"{f[k]['partial']:>8}")
        # The gate that ships belongs in this list. Its single miss is the case
        # the twenty-fourth went looking for, and a miss that is never named is
        # a total; naming it is what lets the reader check the claim.
        for k in ("shipped", "span", "ptext", "punion", "plist"):
            for ex in f[k]["examples"]:
                # A MISSED case is *named*: which page, what the two passes
                # returned, what each reading attributed, and the two facts
                # that explain a zero — where the result came from (`scope`)
                # and whether the loss was ever inside the root (`in_root`).
                print(f"   {k} MISSED: {ex['label']} {ex['url']}\n"
                      f"      clean {ex['clean']:,} kept {ex['kept']:,} "
                      f"(lost {ex['lost']:,})  no-chrome {ex['kept_nc']:,}  "
                      f"rung {ex['rung']}  scope {ex['scope'] or 'none'}\n"
                      f"      attributed: ptext {ex['ptext']:,}  "
                      f"inline {ex['inline']:,}  li {ex['li']:,}  "
                      f"in_root {ex['in_root']:,}  "
                      f"eaten: {_fmt_kinds(ex['kinds'])}")

    print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<12} {why:<40} {url}")


if __name__ == "__main__":
    main()
