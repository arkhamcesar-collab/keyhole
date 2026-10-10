#!/usr/bin/env python
"""Count the loss only where `kept` lives, and see what the region costs.

The fifteenth awakening found the union's no-cost fire and named it, and what it
named was not a mutation: the counter reads the **root**, `kept` reads the
**narrowed span** (the paragraph-tightening rule, fifth awakening), so a
suppression sitting in the part of the root the tightening already discards is
counted as a loss while changing nothing a caller reads. It is visible on an
honest page with no mutation at all — `wikirandom Têgeyştinî Rastî` counts 405
characters of in-root loss whose no-chrome pass returns the *same* text as its
strict pass. And it is older than any mutation: the ninth awakening measured this
same division of two regions, found it explained "only half" of Torrebaja's
firing, and moved to a different counter instead of fixing the region.

It left one candidate, written and unmeasured: **the union inside the span's
region** — the reason (or the prose) counted only where `kept` lives, not in the
whole root. The ninth tried the same-region pairing alone (`span`: both passes,
`lost > kept`), found it weak — 2 misses of 21, fixing Zacatecas and not
Torrebaja — and never tried it as the region of the *disjunction*.

So this probe adds one thing to `probe_gate_pos._PosReader`: every counted
character and every suppression frame carries the containers that were open
around it, and after the parse — using the span the shipped reader actually
chose — each is attributed to inside or outside the region the caller reads. It
is not a second implementation of the tightening: the span is taken from the
`_Ctr` the shipped `_tightest()` returned, and the scope string must name that
same container (`scope.endswith(">" + ctr.label)`) or the probe counts a desync
instead of trusting itself. When a page is not tightened, the region is the
root's own span and every number here is the sibling's — a restriction that can
only remove loss can only remove fires, and if it never removes one it is
measuring nothing.

The mutation is not re-typed either: A is `probe_reason.mutate` (the sibling's
splice, which may land inside a tag) and B is the same seed with the splice
snapped out of tags. Both are printed apart because a changed experiment is a
different experiment, and the fifteenth established that only the pair of them
says which numbers belong to the page.

**Measured: the region is not where the price was, and it costs a catch to learn
it.** 1,500 mutations, same seed, both runs (`--fuzz 1500`):

    run A (the sibling's splice)          caught  missed  no-cost
      union, whole root                      20       0        1
      union, inside the region               19       1        1     <-- worse
      union, whole root, without the CSS     20       0        0
    run B (splice snapped out of tags)    caught  missed  no-cost
      union, whole root                      20       2        2
      union, inside the region               19       3        2     <-- worse
      union, whole root, without the CSS     19       3        0

The region removes one catch and *no* fire, in both runs. It is not that the
region is wrong — 40.2% of the honest corpus's counted loss (16,806 of 41,794
characters, over 62 pages, no mutation involved) is indeed text the caller never
read, and the honest page the fifteenth named is exactly that: `Têgeyştinî Rastî`
counts 405 characters and the region holds **0** of them. It is that the fire does
not live there. What removes it is this probe's one unplanned question, and the
answer is the *eighth awakening's* hole, one level down: `_DROP_TAGS` is applied
by asking `_suppress_why()` first, so a `<style>` that sits *inside* a chrome frame
is pushed as chrome — its CSS arrives as `data`, and `sup_in_root` counts it as
readable text suppression removed. On the honest corpus that is 8,273 characters,
19.8% of everything the counter counts. The union's entire no-cost fire is made of
it: in A a `nav` frame that ate 2,553 characters, 1,466 of them a dropped tag's
payload, and the mis-ended total falls below `kept` (1,087 < 1,661) the moment the
payload is not text. In B it is 1,319 of 1,319 — the whole fire, all CSS.

So the fifteenth's conclusion — that the cause was the region — was **wrong, and
the control that killed it is the same shape as the one that killed the sixth's**:
run the same experiment with the suspect removed. Removing the region changes
nothing; removing the payload removes the fire. What the payload costs instead is
visible on the other axis: A keeps all 20 real truncations, B loses one (20 → 19)
— a real truncation there is caught only because CSS characters inflated a frame
past `kept`. That is a tradeoff, not an improvement, and it is the honest state of
this candidate: **the union's price was never the region; it was the counter
calling CSS prose.** The gate's own Torrebaja fire is untouched by any of this —
its frames all end `matched`, so the union reads 0 there and the shipped counter's
4,400 survives the payload exclusion at 3,291 > 2,752. Two bugs, one shape.

Run:  python tests/probe_region.py [--fuzz N] [--min-chars N]
"""
import importlib.util
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import keyhole  # noqa: E402

DEFAULT_LIST = os.path.join(HERE, "tests", "corpus", "gate_urls.txt")


def _load_sibling(name: str):
    path = os.path.join(HERE, "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pg = _load_sibling("probe_gate")
_pr = _load_sibling("probe_rules")
_gp = _load_sibling("probe_gate_pos")
_rs = _load_sibling("probe_reason")

_PosReader = _gp._PosReader
mutate = _rs.mutate           # the same experiment, not a copy of its shape
by_how = _rs.by_how


class _SpanReader(_PosReader):
    """A `_PosReader` that knows which of its own loss the caller reads.

    The tightening is chosen *after* the parse (`_Reader._apply_scope`, from
    `close()`), so nothing can be attributed while the tags are being read. What
    is recorded instead is the identity of the containers open around each piece
    of loss — cheap, and it survives the reordering the scope does to the output
    streams (a text-index window would not: the streams are sliced by the span,
    so an index read during the parse is in different coordinates than the span
    it is compared against).

    `_tightest` is *captured*, not reimplemented: this subclass learns which
    container the shipped rule picked by overriding the method and keeping its
    return value. A probe that recomputed the rule could disagree with the reader
    about the region — the fifth awakening's sin, measuring with an instrument
    *like* the one being built — and the only check that would catch it is the
    one that is here instead: the scope string the shipped reader produced must
    name the container this probe is using.
    """

    def __init__(self, scope: bool = True):
        super().__init__(scope)
        self._span_ctr = None
        self._chunks: list[tuple[tuple, str, int, bool]] = []
        self._chunk_total = 0      # running sum, checked against the shipped counter
        self._frame_total = 0      # ... and against the frames' own accounting
        self.sup_drop = 0          # counted chars that are a dropped tag's payload
        self.desync = 0            # counted chars != the shipped counter
        self.frame_desync = 0      # ... and != the frames' own sum
        self.label_mismatch = 0    # the scope does not name the captured span

    def _tightest(self, *a):
        best = super()._tightest(*a)
        self._span_ctr = best
        return best

    def handle_starttag(self, tag, attrs):
        n = len(self.frames)
        super().handle_starttag(tag, attrs)
        if len(self.frames) > n:
            # the frame this tag opened: which containers enclose the suppression
            self.frames[-1]["ctrs"] = tuple(self._ctr)
            self.frames[-1]["drop"] = 0

    def handle_data(self, data):
        # Same condition the shipped `_Reader.handle_data` counts with — copied
        # on purpose, because the region split needs the per-chunk records the
        # shipped counter throws away. The copy is checked rather than trusted:
        # the chunks must add up to `sup_in_root` on every parse, and a mismatch
        # is counted here (and named in the output) instead of being summed.
        if (data.strip() and self._suppress_why() == "chrome"
                and self._in_root_region()):
            kind = "p" if self._sup_p else (self._marks[-1] if self._marks else "other")
            # A tag whose payload is not text — `<style>`, `<script>` — is dropped
            # by `_DROP_TAGS`, but *only when nothing else is already suppressing*:
            # `handle_starttag` reads `_suppress_why()` first, so a `<style>` that
            # lives inside a chrome frame is pushed as chrome, its CSS arrives as
            # data, and `sup_in_root` counts it as readable text suppression
            # removed. The eighth awakening fixed exactly this confusion between
            # `drop` and `chrome` — but only for the innermost reason, which is
            # why the fix has this hole. Counted here to be measured, not assumed.
            in_drop = any(t in keyhole._DROP_TAGS for t, _ in self._stack)
            self._chunks.append((tuple(self._ctr), kind, len(data), in_drop))
            self._chunk_total += len(data)
            if in_drop:
                self.sup_drop += len(data)
            if self._chunk_total != self.sup_in_root + len(data):
                self.desync += 1
            for f in reversed(self.frames):
                if f["how"] is None:
                    self._frame_total += len(data)
                    if in_drop:
                        f["drop"] += len(data)
                    break
        super().handle_data(data)

    def close(self):
        super().close()
        if self._frame_total != sum(f["chars"] for f in self.frames):
            self.frame_desync += 1


def region_of(pos) -> str:
    """The container the caller reads, or "" when the root's span is the region.

    The scope string is the shipped reader's own answer, so this cannot drift
    from what the reader did: a tightening that was abandoned falls back to the
    root's name, which carries no ">".
    """
    if pos._span_ctr is not None and ">" in pos.scope:
        return pos._span_ctr.label
    return ""


def in_region(pos, ctrs, region: str) -> bool:
    if not region:
        return True
    return any(c is pos._span_ctr for c in ctrs)


def candidates(html: str) -> dict:
    """The sibling's readings, plus every one of them restricted to the region."""
    m = _pg.measure(html)
    kept = m["kept"]
    pos = keyhole._reader(html, _SpanReader)
    floor = keyhole.EMPTY_TEXT
    region = region_of(pos)
    if region and not pos.scope.endswith(">" + region):
        pos.label_mismatch += 1

    in_ptext = out_ptext = in_kind = out_kind = 0
    in_drop = out_drop = 0
    in_ptext_nd = drop_ptext = 0
    for ctrs, kind, chars, is_drop in pos._chunks:
        here = in_region(pos, ctrs, region)
        if here:
            in_drop += chars if is_drop else 0
        else:
            out_drop += chars if is_drop else 0
        if kind == "p":
            if is_drop:
                drop_ptext += chars
            if here:
                in_ptext += chars
                in_ptext_nd += 0 if is_drop else chars
            else:
                out_ptext += chars
        elif here:
            in_kind += chars
        else:
            out_kind += chars

    in_mishap = out_mishap = in_mishap_nd = 0
    for f in pos.frames:
        f["in_region"] = in_region(pos, f["ctrs"], region)
        if f["how"] == "matched":
            continue
        if f["in_region"]:
            in_mishap += f["chars"]
            in_mishap_nd += f["chars"] - f["drop"]
        else:
            out_mishap += f["chars"]

    root_ptext = pos.sup_ptext
    # `probe_gate_pos` names this reading `open`, and `probe_reason` asserts it is
    # character for character the same expression as its own `mishap`.
    root_mishap = sum(f["chars"] for f in pos.frames if f["how"] != "matched")
    root_mishap_nd = sum(f["chars"] - f["drop"] for f in pos.frames
                         if f["how"] != "matched")
    root_drop = pos.sup_drop
    ptext_fires = root_ptext > kept and root_ptext > floor
    reason_fires = root_mishap > kept and root_mishap > floor
    span_ptext_fires = in_ptext > kept and in_ptext > floor
    span_reason_fires = in_mishap > kept and in_mishap > floor
    nodrop_fires = ((root_ptext - drop_ptext) > kept
                    and (root_ptext - drop_ptext) > floor) \
        or (root_mishap_nd > kept and root_mishap_nd > floor)
    span_nodrop_fires = (in_ptext_nd > kept and in_ptext_nd > floor) \
        or (in_mishap_nd > kept and in_mishap_nd > floor)
    return {
        "kept": kept,
        "kept_nc": len(keyhole._text_of(keyhole._reader(html, keyhole._NoChromeReader))),
        "scope": m["scope"], "rung": m["rung"],
        "region": region,
        "sup_in_root": m["drop_in_root"],
        "sup_ptext": root_ptext, "sup_open": root_mishap,
        "in_ptext": in_ptext, "out_ptext": out_ptext,
        "in_kind": in_kind, "out_kind": out_kind,
        "in_mishap": in_mishap, "out_mishap": out_mishap,
        "in_loss": in_ptext + in_kind, "out_loss": out_ptext + out_kind,
        "sup_drop": root_drop, "in_drop": in_drop, "out_drop": out_drop,
        "drop_ptext": drop_ptext,
        "root_mishap_nd": root_mishap_nd, "in_mishap_nd": in_mishap_nd,
        "desync": pos.desync, "frame_desync": pos.frame_desync,
        "label_mismatch": pos.label_mismatch,
        "shipped_share": m["ratio"], "shipped_fires": m["ate"],
        "ptext_fires": ptext_fires, "reason_fires": reason_fires,
        "union_fires": ptext_fires or reason_fires,
        "span_ptext_fires": span_ptext_fires,
        "span_reason_fires": span_reason_fires,
        "span_union_fires": span_ptext_fires or span_reason_fires,
        "nodrop_fires": nodrop_fires,
        "span_nodrop_fires": span_nodrop_fires,
        "frames": pos.frames, "sup_kind": pos.kinds(),
    }


# The readings, in the order they are scored: the three the fifteenth awakening
# measured over the whole root, the same three inside the region the caller reads,
# and the union with the dropped tags' own payload (CSS, JS) excluded — the hole
# the eighth awakening's fix for the counter's cause leaves open one level down.
CANDIDATES = ("ptext", "reason", "union", "span_ptext", "span_reason",
              "span_union", "nodrop", "span_nodrop")
FIRES = {k: f"{k}_fires" for k in CANDIDATES}


def fuzz(pages, clean_kept, rounds, seed=0, untag=False):
    """Score every reading on the same mutations, under the truth that reads the
    *page* (`probe_gate_pos`'s: the mutation lost more than half of what the same
    page returned clean, and still returned something readable).

    The scoring is the sibling's, so the three whole-root columns reproduce
    `probe_reason`'s numbers and the region columns are comparable with them —
    which is the only way the price of a narrower region can be read off the same
    rows it is paid on.
    """
    rnd = random.Random(seed)
    out = {k: {"caught": 0, "missed": 0, "no_cost": 0, "partial": 0, "examples": []}
           for k in CANDIDATES}
    out.update({"n": 0, "real": 0, "silent": 0, "desync": 0, "frame_desync": 0,
                "no_region": 0, "in_loss": 0, "out_loss": 0, "drop": 0,
                "drop_ptext": 0, "no_cost_examples": [],
                "miss_examples": []})
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
        if c["desync"] or c["frame_desync"]:
            out["desync"] += 1
        if not c["region"]:
            out["no_region"] += 1
        out["in_loss"] += c["in_loss"]
        out["out_loss"] += c["out_loss"]
        out["drop"] += c["sup_drop"]
        out["drop_ptext"] += c["drop_ptext"]
        lost = max(0, clean - c["kept"])
        real = lost > clean * 0.5 and lost > keyhole.EMPTY_TEXT and c["kept"] > keyhole.EMPTY_TEXT
        if real:
            out["real"] += 1
            if c["rung"] == "strict":
                out["silent"] += 1
        for k in CANDIDATES:
            slot = out[k]
            if c[FIRES[k]]:
                if real:
                    slot["caught"] += 1
                elif lost > 0:
                    slot["partial"] += 1
                else:
                    slot["no_cost"] += 1
                    if k == "span_union" and len(out["no_cost_examples"]) < 8:
                        out["no_cost_examples"].append({
                            "label": label, "clean": clean, "kept": c["kept"],
                            "scope": c["scope"], "region": c["region"],
                            "in_loss": c["in_loss"], "out_loss": c["out_loss"],
                            "in_ptext": c["in_ptext"], "in_mishap": c["in_mishap"],
                            "sup_drop": c["sup_drop"], "in_drop": c["in_drop"],
                            "eaten": dict(c["sup_kind"]),
                            "frames": [(f["chars"], f["label"], f["how"],
                                        f["in_region"], f["drop"])
                                       for f in sorted(c["frames"],
                                                       key=lambda f: -f["chars"])[:3]],
                        })
            elif real:
                slot["missed"] += 1
                if k == "span_union":
                    if len(out["miss_examples"]) < 8:
                        out["miss_examples"].append({
                            "label": label, "clean": clean, "kept": c["kept"],
                            "lost": lost, "scope": c["scope"], "region": c["region"],
                            "in_loss": c["in_loss"], "out_loss": c["out_loss"],
                            "in_ptext": c["in_ptext"], "in_mishap": c["in_mishap"],
                            "root_ptext": c["sup_ptext"],
                            "root_mishap": c["sup_open"],
                            "eaten": dict(c["sup_kind"]),
                        })
    return out


def fmt_kinds(kinds) -> str:
    if not kinds:
        return "-"
    return " ".join(f"{k}:{v}" for k, v in
                    sorted(kinds.items(), key=lambda kv: -kv[1]) if v)


def report(f, title, note):
    print(f"\n== {title}")
    print(f"   {note}")
    print(f"   mutations scored:                    {f['n']}")
    print(f"   the mutation really ate the article:  {f['real']}"
          f"   of those silent (parse=strict): {f['silent']}")
    print(f"   pages with no tightening (region = root's own span): {f['no_region']}"
          f"   — the region test is vacuous there")
    print(f"   counted loss, inside the region: {f['in_loss']:,}"
          f"   outside it: {f['out_loss']:,}"
          f"   ({f['out_loss'] * 100 / max(1, f['in_loss'] + f['out_loss']):.1f}%"
          f" of the root's loss is text no caller read)")
    print(f"   parses where the chunk copy drifted from sup_in_root / the frames: "
          f"{f['desync']}   (must be 0)")
    print(f"\n   {'reading':<44} {'caught':>7} {'missed':>7} {'no-cost':>8} {'partial':>8}")
    for k, lbl in (("ptext", "prose eaten (whole root)"),
                   ("reason", "a suppression mis-ended (whole root)"),
                   ("union", "either, whole root"),
                   ("span_ptext", "prose eaten, inside the region"),
                   ("span_reason", "mis-ended, inside the region"),
                   ("span_union", "either, inside the region"),
                   ("nodrop", "either, whole root, without the CSS/JS"),
                   ("span_nodrop", "either, inside the region, without the CSS")):
        s = f[k]
        print(f"   {lbl:<44} {s['caught']:>7} {s['missed']:>7} {s['no_cost']:>8} "
              f"{s['partial']:>8}")

    print(f"\n   the region union's no-cost fire, named (not counted): "
          f"{f['span_union']['no_cost']}")
    for ex in f["no_cost_examples"]:
        print(f"     {ex['label']:<12} clean {ex['clean']:,}  kept {ex['kept']:,}  "
              f"in_region {ex['in_loss']:,}  out {ex['out_loss']:,}  "
              f"(ptext {ex['in_ptext']:,}  mishap {ex['in_mishap']:,})")
        print(f"         scope {ex['scope'] or 'none'}   region {ex['region'] or '-'}"
              f"   eaten: {fmt_kinds(ex['eaten'])}")
        print(f"         of the counted loss, a dropped tag's payload (CSS/JS read as "
              f"text): {ex['sup_drop']:,}  of it inside the region {ex['in_drop']:,}")
        for chars, label, how, inn, drop in ex["frames"]:
            print(f"         {chars:>7}  {label:<28} ended {how:<8} region: "
                  f"{'in ' if inn else 'out'}  of which drop {drop:,}")
    if not f["no_cost_examples"]:
        print(f"     (none)")

    print(f"\n   the real truncations the region union misses, named: "
          f"{f['span_union']['missed']}")
    for ex in f["miss_examples"]:
        print(f"     {ex['label']:<12} clean {ex['clean']:,}  kept {ex['kept']:,}  "
              f"lost {ex['lost']:,}  scope {ex['scope'] or 'none'}")
        print(f"         in_region {ex['in_loss']:,} (ptext {ex['in_ptext']:,} "
              f"mishap {ex['in_mishap']:,})  outside {ex['out_loss']:,}   "
              f"whole root: ptext {ex['root_ptext']:,} mishap {ex['root_mishap']:,}")
        print(f"         eaten: {fmt_kinds(ex['eaten'])}")
    if not f["miss_examples"]:
        print(f"     (none)")


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
    print(f"keyhole {keyhole.__version__} — the loss the caller reads, and the loss "
          f"only the counter can see\n"
          f"corpus: {len(urls)} urls (uncurated + the nine the gate was built on)   "
          f"mutations: {rounds or '-'}\n")

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
            skipped.append((src, url, f"no region ({c['kept']} kept)"))
            continue
        rows.append({"src": src, "url": url, **c})

    # Same order the siblings fuzz in — the fuzz indexes into this list, so a
    # different order is a different sample of the same experiment.
    rows.sort(key=lambda r: -r["shipped_share"])
    print(f"{'src':<12} {'kept':>7} {'in_root':>8} {'in_reg':>7} {'out_reg':>8} "
          f"{'ptext':>7} {'mishap':>7} {'drop':>7} {'desync':>7}  fires  scope")
    print("-" * 126)
    for r in sorted(rows, key=lambda r: -r["out_loss"])[:24]:
        fires = "".join(x if r[k] else "-" for k, x in
                        (("shipped_fires", "S"), ("ptext_fires", "P"),
                         ("reason_fires", "O"), ("union_fires", "U"),
                         ("span_ptext_fires", "p"), ("span_reason_fires", "o"),
                         ("span_union_fires", "u"), ("nodrop_fires", "N"),
                         ("span_nodrop_fires", "n")))
        print(f"{r['src']:<12} {r['kept']:>7} {r['sup_in_root']:>8} "
              f"{r['in_loss']:>7} {r['out_loss']:>8} {r['in_ptext']:>7} "
              f"{r['in_mishap']:>7} {r['sup_drop']:>7} {r['desync']:>7}  "
              f"{fires:<9} {r['scope'][:40] or 'none'}")

    tot_in = sum(r["in_loss"] for r in rows)
    tot_out = sum(r["out_loss"] for r in rows)
    tot_drop = sum(r["sup_drop"] for r in rows)
    print(f"\n== {len(rows)} measurable pages  ({len(skipped)} left out, named below)")
    print(f"   counted loss on the honest corpus: in_root "
          f"{sum(r['sup_in_root'] for r in rows):,}  "
          f"= inside the region {tot_in:,} + outside it {tot_out:,}"
          f"   ({tot_out * 100 / max(1, tot_in + tot_out):.1f}% outside)")
    print(f"   of the counted loss, a dropped tag's own payload (CSS/JS read as "
          f"text): {tot_drop:,}"
          f"   ({tot_drop * 100 / max(1, sum(r['sup_in_root'] for r in rows)):.1f}%"
          f" of everything the counter counts)")
    print(f"   parses where the chunk copy drifted from sup_in_root: "
          f"{sum(r['desync'] for r in rows)}   "
          f"scope/span label mismatches: {sum(r['label_mismatch'] for r in rows)}")
    print(f"   pages with no tightening at all: "
          f"{len([r for r in rows if not r['region']])}   "
          f"(the region test cannot change their numbers)")

    print(f"\n== fires on the honest corpus  (S=shipped  P=ptext  O=reason  U=union"
          f"  p/o/u = the same inside the region  N/n = union without the CSS)")
    for k in ("shipped_fires", "ptext_fires", "reason_fires", "union_fires",
              "span_ptext_fires", "span_reason_fires", "span_union_fires",
              "nodrop_fires", "span_nodrop_fires"):
        hit = [r for r in rows if r[k]]
        print(f"   {k.replace('_fires', ''):<18} {len(hit)}")
        for r in hit:
            print(f"     ↳ {r['src']:<12} kept {r['kept']:,}  in_root "
                  f"{r['sup_in_root']:,}  in_reg {r['in_loss']:,}  out "
                  f"{r['out_loss']:,}  drop {r['sup_drop']:,}  scope "
                  f"{r['scope'][:38] or 'none'}  {r['url']}")
            for fr in sorted(r["frames"], key=lambda f: -f["chars"])[:3]:
                where = "in " if fr["in_region"] else "out"
                print(f"         {fr['chars']:>7}  {fr['label']:<28} ended "
                      f"{fr['how']:<8} region: {where}  of which drop {fr['drop']:,}")

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

    f_a = fuzz(pages, clean_kept, rounds)
    f_b = fuzz(pages, clean_kept, rounds, untag=True)
    report(f_a, f"fuzz A — {rounds} mutations, the sibling's splice (may land inside a tag)",
           "the shape probe_gate_pos, probe_reason and probe_truncation measure with")
    report(f_b, f"fuzz B — same seed, splice snapped out of tags (*a different experiment*)",
           "same anchors, same rule, same rounds; only offsets inside a tag moved")

    print(f"\n== what the region costs, and what the CSS costs (A vs. B, same seed)")
    print(f"   {'reading':<44} {'A caught':>9} {'B caught':>9} {'A no-cost':>10} "
          f"{'B no-cost':>10}")
    for k, lbl in (("ptext", "prose eaten (whole root)"),
                   ("reason", "mis-ended (whole root)"),
                   ("union", "either, whole root"),
                   ("span_ptext", "prose eaten, inside the region"),
                   ("span_reason", "mis-ended, inside the region"),
                   ("span_union", "either, inside the region"),
                   ("nodrop", "either, whole root, without the CSS/JS"),
                   ("span_nodrop", "either, inside the region, without the CSS")):
        a, b = f_a[k], f_b[k]
        print(f"   {lbl:<44} {a['caught']:>9} {b['caught']:>9} {a['no_cost']:>10} "
              f"{b['no_cost']:>10}")
    print(f"   mutations that really ate the article: A {f_a['real']}  B {f_b['real']}"
          f"   loss outside the region: A {f_a['out_loss']:,}  B {f_b['out_loss']:,}"
          f" chars")
    print(f"   counted loss that is a dropped tag's payload (CSS/JS read as text): "
          f"A {f_a['drop']:,}  B {f_b['drop']:,} chars")

    print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<12} {why:<40} {url}")


if __name__ == "__main__":
    main()
