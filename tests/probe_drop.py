#!/usr/bin/env python
"""Does the shipped gate have the same hole? Ask the shipped gate.

The sixteenth awakening found the counter calling CSS prose: `_DROP_TAGS` is
applied by asking `_suppress_why()` *first*, so a `<style>` (or `<script>`)
sitting inside a chrome frame is pushed as chrome, its payload arrives as `data`,
and `sup_in_root` counts it as readable text suppression removed. On the honest
corpus that is 8,273 characters, 19.8% of everything the counter counts.

It measured that on the *union* candidate — a reading that is not shipped. The
question it left open is the one that decides whether any of this changes the
tool: **the gate that ships has the same counter, so does it have the same
hole?** Torrebaja is the case the sixteenth checked by hand (4,400 in-root,
1,109 of it payload, 3,291 still > 2,752 kept — the fire survives), and one case
checked by hand is not a corpus. What is unresolved is the whole distribution:

  * on the honest corpus, how many pages' shares move when the payload is not
    text, and does any of them cross `ATE_ROOT` in either direction — a page the
    filter *saves* from a false relaxation, or one it *pushes* into a false one;
  * under the mutation, of the shipped gate's 34 no-cost fires, how many exist
    only because CSS was being read as prose, and how many real truncations the
    same exclusion stops catching.

That is a candidate measured against the shipped gate, which is the only
comparison that can end in a change to `keyhole.py`. Nothing here touches the
shipped file: the counter is copied into a subclass, and the copy is checked
against the shipped `sup_in_root` on every parse (a drift is counted and named,
never summed).

The instrument is the sibling's, not a likeness of it. `probe_gate_pos` supplies
the mutation, the grading truth (the mutation ate the article when the strict
pass lost more than half of what the *same page* returned clean — a truth that
reads no candidate), the scoring, and the page order; this probe adds one entry
to its candidate tuple and swaps its `candidates()` for one that also reports
the shipped counter with the payload out. So the run must reproduce that probe's
published rows for the readings it shares — `shipped` 20/20 caught with 34
no-cost, `ptext` 18/20 with 0, `plist` 19/20 with 24 — or it is measuring a
different experiment, and it says so at the end.

The two numbers the shipped gate is asked for are asked of the shipped *functions*
and not of copies: `keyhole.root_lost_share` and `keyhole.ate_the_root` are called
twice on the same reader, once with `sup_in_root` as the parser left it and once
with it replaced by the payload-free count. The rule that decides is neither
re-typed nor re-tuned; only the number it reads changes.

**Measured: the hole is in the gate that ships, and closing it improves the gate
strictly — by ten fires, none of them a catch.** 62 honest pages and the same
1,500 mutations: the control reproduces `probe_gate_pos`'s published rows exactly
(`shipped` 20 caught / 34 no-cost, `ptext` 18/0, `plist` 19/24), so this run is
that experiment and not another one.

    honest corpus (62 pages)         counted   payload      max share   fires
      the gate as it ships            41,794     8,273        61.5%        1
      the gate without the payload    33,521         0        54.5%        1

  * 8 of the 62 pages carry any payload at all, and the payload is `<style>`
    (Wikipedia), `<script>` and `<svg>` (unison-lang): not one character of it is
    prose. Naming the owning tag is not decoration — `<svg>` and `<noscript>`
    *can* hold text a reader would see, so "payload" is measured here, not
    assumed.
  * **no honest page's fire flips, in either direction.** Torrebaja is the only
    honest fire and it survives: 4,400 in-root, 1,109 of it `<style>`, 3,291
    still > 2,752 kept — 61.5% → 54.5%, over the threshold either way. The page
    whose share moves the most is an HN article: share 40.3% → 14.9%.

    under mutation (1,500)         caught  missed  no-cost  partial
      shipped                         20       0       34       14
      shipped, without the payload    20       0       24       14

  * The exclusion removes **10 fires and nothing else**: not one real truncation
    stops being caught and not one partial fire goes away. It is the first
    reading measured against the gate it would replace that is a *strict*
    improvement — and it also dominates `plist` (19 caught, 24 no-cost) on the
    same rows, which is where the eleventh awakening's door was left.
  * The ten are named, and they are two shapes: nine are a `nav#main-nav` frame
    on the unison-lang page (632–5,182 characters of `<script>` and `<svg>` in a
    nav the mutation had pushed into chrome) and one is the `nav` frame the
    fifteenth and sixteenth both named — 2,553 characters, 1,466 of them CSS from
    a `<style>` the mutation left unparsed.

**What this is not.** The probe measures the *counter*; the fix that would ship is
one line in `handle_starttag` — a tag in `_DROP_TAGS` is pushed as `drop` even
when a chrome frame is already suppressing — and the two are equal by
`_suppress_why()`'s own rule (it returns the innermost non-empty reason, and a
chrome frame can never be opened inside a drop frame, because the reason there is
already non-empty), not by measurement. That is an argument, and it is written
here as one. Nothing in `keyhole.py` was touched: this is an instrument and a
number, and the change it argues for is not made on the strength of a probe.

Run:  python tests/probe_drop.py [--fuzz N] [--min-chars N] [--order=url]

`--order=url` pins the page order on the URL instead of on `shipped_share`, so
the fuzz indexes the same page before and after a change to the counter and both
runs score the *same* mutations. Without it the probe can only compare two
readings inside one run; with it, it can compare two runs. The 1,500 mutations
are not re-drawn to make a point — the digest printed under the header is what
says they were not.
"""
import hashlib
import importlib.util
import os
import statistics
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


_gp = _load_sibling("probe_gate_pos")

# The sibling's experiment with one candidate added — not one re-typed. The
# mutation, the truth, the scoring and the page order all stay its own, so the
# rows it already published are a control on this run rather than a memory of it.
_gp.CANDIDATES = tuple(_gp.CANDIDATES) + ("shipped_nodrop",)
_orig_candidates = _gp.candidates

# Set by main() before the fuzz runs, so the recorder below can say *which page*
# a removed fire came from. Recovering it is the only honest option: the fuzz
# picks its page with its own RNG and never passes the name to `candidates`, and
# re-typing the mutation here to find out would be measuring a copy of the
# experiment instead of the experiment.
PAGES: list = []
_removed: list[dict] = []   # the fires the exclusion takes away, named


def _which_page(data: str, cap: int = 4096) -> tuple[str, int]:
    """The page a mutated document was cut from, by longest common prefix.

    The mutation splices at an offset without touching what precedes it, so the
    first `a` characters are the page's own. Two pages can share the cap when
    the splice lands very early; the length is returned so that is visible
    rather than assumed.
    """
    best, ln = "?", 0
    for h, lbl in PAGES:
        n = min(len(h), len(data), cap)
        i = 0
        while i < n and h[i] == data[i]:
            i += 1
        if i > ln:
            best, ln = lbl, i
    return best, ln

# What `probe_gate_pos` published for the 1,500-mutation run, as (caught, no-cost).
# Reproduced here or this run is a different experiment and says so.
CONTROL = {"shipped": (20, 34), "ptext": (18, 0), "plist": (19, 24)}


class _DropReader(_gp._PosReader):
    """The shipped counter, and the same counter with a dropped tag's payload out.

    Both counts are kept, and the *condition* is copied from
    `keyhole._Reader.handle_data` on purpose — the region split needs a second
    accumulator, and the shipped counter throws its characters away. A copy is
    checked rather than trusted: the two must add up to the shipped
    `sup_in_root` after every counted chunk, and any chunk where they do not is
    counted here and named in the output instead of being summed.

    What makes a chunk a payload is the *whole* stack, not the innermost reason:
    `_suppress_why()` walks the stack in reverse and stops at the first frame
    that says anything, so a `<style>` inside a `<div class="sidebar">` reports
    `chrome` and its bytes are read as words. A tag from `_DROP_TAGS` anywhere
    below it is what the eighth awakening's distinction (drop vs. chrome) was
    for; the inner reason is not.
    """

    def __init__(self, scope: bool = True):
        super().__init__(scope)
        self.sup_nodrop = 0     # the shipped condition, payload excluded
        self.sup_payload = 0    # ... and only the payload it excluded
        self.payload_tags: dict[str, int] = {}   # ... by the tag that owns it
        self.desync = 0         # counted chunks where the copy drifted

    def handle_data(self, data):
        counted = bool(data.strip()) and self._suppress_why() == "chrome" \
            and self._in_root_region()
        drops = [t for t, _ in self._stack if t in keyhole._DROP_TAGS]
        payload = counted and bool(drops)
        super().handle_data(data)
        if not counted:
            return
        if self.sup_nodrop + self.sup_payload + len(data) != self.sup_in_root:
            self.desync += 1
        if payload:
            self.sup_payload += len(data)
            # Named by the *owning* tag and not just called "CSS": `<svg>` and
            # `<noscript>` can hold text a reader would see, so what the payload
            # is made of decides whether calling it unreadable is true or a
            # second assumption wearing the first one's clothes.
            self.payload_tags[drops[-1]] = self.payload_tags.get(drops[-1], 0) + len(data)
        else:
            self.sup_nodrop += len(data)
        for f in reversed(self.frames):
            if f["how"] is None:
                f["payload"] = f.get("payload", 0) + (len(data) if payload else 0)
                break


def nodrop(html: str) -> dict:
    """The shipped gate, asked twice: as it ships, and with the payload not text."""
    p = keyhole._reader(html, _DropReader)
    shipped_share = keyhole.root_lost_share(p)
    shipped_fires = keyhole.ate_the_root(p)
    p.sup_in_root = p.sup_nodrop          # the shipped rule, the other number
    return {
        "sup_nodrop": p.sup_nodrop,
        "sup_payload": p.sup_payload,
        "payload_tags": p.payload_tags,
        "shipped_nodrop_share": keyhole.root_lost_share(p),
        "shipped_nodrop_fires": keyhole.ate_the_root(p),
        "shipped_share_check": shipped_share,
        "shipped_fires_check": shipped_fires,
        "desync": p.desync,
        "frames": p.frames,
    }


def candidates(html: str) -> dict:
    """The sibling's readings, untouched, plus the shipped counter without payload.

    Every call the fuzz makes passes through here, so the fires the exclusion
    takes away are recorded where they happen rather than reconstructed
    afterwards — no second run, no second experiment.
    """
    c = dict(_orig_candidates(html))
    c.update(nodrop(html))
    if PAGES and c["shipped_fires"] and not c["shipped_nodrop_fires"] \
            and len(_removed) < 40:
        lbl, lcp = _which_page(html)
        _removed.append({
            "label": lbl, "lcp": lcp, "kept": c["kept"], "kept_nc": c["kept_nc"],
            "in_root": c["sup_in_root"], "payload": c["sup_payload"],
            "nodrop": c["sup_nodrop"], "scope": c["scope"],
            "payload_tags": dict(c["payload_tags"]),
            "frames": [(f["chars"], f["label"], f["how"], f.get("payload", 0))
                       for f in sorted(c["frames"], key=lambda f: -f["chars"])[:3]],
        })
    return c


_gp.candidates = candidates


def fmt(vals) -> str:
    if not vals:
        return "-"
    return (f"max {max(vals) * 100:.1f}%  p90 {vals[int(len(vals) * .9)] * 100:.1f}%  "
            f"median {statistics.median(vals) * 100:.1f}%")


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

    urls = _gp._pg.read_list(path) + [(f"old-{n}", u) for n, u in
                                      [(s.replace(".", ""), u) for s, u in _gp._pr.SITES]]
    print(f"keyhole {keyhole.__version__} — the shipped gate's own counter, asked "
          f"with and without a dropped tag's payload\n"
          f"corpus: {len(urls)} urls (uncurated + the nine the gate was built on)   "
          f"mutations: {rounds or '-'}\n")

    rows, skipped = [], []
    for src, url in urls:
        if not _gp._pg.is_html(url):
            skipped.append((src, url, "not html"))
            continue
        try:
            html = _gp._pg.cached_download(url)
        except Exception as e:
            skipped.append((src, url, f"{type(e).__name__}"[:30]))
            continue
        c = candidates(html)
        if c["kept"] < floor or not c["scope"]:
            skipped.append((src, url, f"no region ({c['kept']} kept)"))
            continue
        rows.append({"src": src, "url": url, **c})

    # The sibling's own order — the fuzz indexes into this list, so a different
    # order is a different sample of the same experiment.
    #
    # That is the trap the eighteenth awakening walked into and named: the
    # sibling sorts by `shipped_share`, which is the number under test, so
    # changing the counter re-sorts the list and the fuzz — which picks its page
    # by index — re-rolls its mutations. Two runs of the *same* probe and the
    # same 1,500 rounds then score two different mutation sets, and *before vs.
    # after* is not available, only *this vs. that*. `--order=url` pins the
    # order on a key the counter cannot move, so the same index is the same page
    # in both runs and the sample is shared. The sample digest below is the
    # witness: same digest, same mutations, and the only thing that changed is
    # the counter.
    pinned = "--order=url" in sys.argv
    rows.sort(key=(lambda r: r["url"]) if pinned else (lambda r: -r["shipped_share"]))
    _seq = "|".join(f"{r['src']}:{r['url']}" for r in rows)
    print(f"   page order: {len(rows)} pages "
          + ("pinned by url — invariant to the counter under test"
             if pinned else "by shipped_share — the number under test")
          + f"   sample digest {hashlib.sha256(_seq.encode()).hexdigest()[:16]}")

    moved = [r for r in rows if abs(r["shipped_share"] - r["shipped_nodrop_share"]) > 1e-12]
    saved = [r for r in rows if r["shipped_fires"] and not r["shipped_nodrop_fires"]]
    made = [r for r in rows if r["shipped_nodrop_fires"] and not r["shipped_fires"]]
    payload_pages = [r for r in rows if r["sup_payload"]]

    print(f"{'src':<12} {'kept':>7} {'in_root':>8} {'payload':>8} {'nodrop':>8} "
          f"{'share':>7} {'no-drop':>8} {'scope':>6}  fires")
    print("-" * 92)
    for r in rows[:24]:
        fires = ("S" if r["shipped_fires"] else "-") + ("N" if r["shipped_nodrop_fires"] else "-")
        print(f"{r['src']:<12} {r['kept']:>7} {r['sup_in_root']:>8} {r['sup_payload']:>8} "
              f"{r['sup_nodrop']:>8} {r['shipped_share'] * 100:>6.1f}% "
              f"{r['shipped_nodrop_share'] * 100:>7.1f}% {'yes' if r['scope'] else 'no':>6}  "
              f"{fires}  {r['scope'][:34] or 'none'}")

    tot_root = sum(r["sup_in_root"] for r in rows)
    tot_pay = sum(r["sup_payload"] for r in rows)
    print(f"\n== {len(rows)} measurable pages  ({len(skipped)} left out, named below)")
    print(f"   counted loss on the honest corpus: {tot_root:,}"
          f"   of it a dropped tag's payload: {tot_pay:,}"
          f"   ({tot_pay * 100 / max(1, tot_root):.1f}% of everything the counter counts)")
    print(f"   pages where that payload is > 0:              {len(payload_pages)} of {len(rows)}")
    tags: dict[str, int] = {}
    for r in rows:
        for t, n in r["payload_tags"].items():
            tags[t] = tags.get(t, 0) + n
    print(f"   the payload, by the tag that owns it:         "
          + "   ".join(f"<{t}> {n:,}" for t, n in sorted(tags.items(), key=lambda kv: -kv[1])))
    print(f"   pages whose share moves at all:               {len(moved)}")
    print(f"   pages the filter SAVES from a relaxation:     {len(saved)}")
    print(f"   pages the filter PUSHES into one:             {len(made)}")
    print(f"   shares, shipped:     {fmt(sorted(r['shipped_share'] for r in rows))}")
    print(f"   shares, no payload:  {fmt(sorted(r['shipped_nodrop_share'] for r in rows))}")
    print(f"   parses where the counter copy drifted from sup_in_root: "
          f"{sum(r['desync'] for r in rows)}   (must be 0)")
    for r in saved + made:
        why = "saved" if r in saved else "pushed in"
        print(f"\n   {why}: {r['url']}")
        print(f"     kept {r['kept']:,}  in_root {r['sup_in_root']:,} "
              f"(payload {r['sup_payload']:,}) → nodrop {r['sup_nodrop']:,}   "
              f"share {r['shipped_share'] * 100:.1f}% → {r['shipped_nodrop_share'] * 100:.1f}%"
              f"   threshold 50%")
        for f in sorted(r["frames"], key=lambda f: -f["chars"])[:3]:
            print(f"     {f['chars']:>7}  {f['label']:<28} ended {f['how']:<8} "
                  f"of which payload {f.get('payload', 0):,}")

    print(f"\n== fires on the honest corpus  (S=shipped  N=shipped without the payload)")
    for k in ("shipped_fires", "shipped_nodrop_fires"):
        hit = [r for r in rows if r[k]]
        print(f"   {k.replace('_fires', ''):<18} {len(hit)}")
        for r in hit:
            print(f"     ↳ {r['src']:<12} kept {r['kept']:,}  in_root {r['sup_in_root']:,}  "
                  f"payload {r['sup_payload']:,}  nodrop {r['sup_nodrop']:,}  "
                  f"share {r['shipped_share'] * 100:.1f}% → "
                  f"{r['shipped_nodrop_share'] * 100:.1f}%  {r['url']}")
            for f in sorted(r["frames"], key=lambda f: -f["chars"])[:3]:
                print(f"         {f['chars']:>7}  {f['label']:<28} ended {f['how']:<8} "
                      f"of which payload {f.get('payload', 0):,}")

    if not rounds:
        print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
        for src, url, why in skipped:
            print(f"   {src:<12} {why:<40} {url}")
        return

    pages, clean_kept = [], []
    for r in rows:
        try:
            html = _gp._pg.cached_download(r["url"])
        except Exception:
            continue
        pages.append((html, r["src"]))
        clean_kept.append(candidates(html)["kept"])

    PAGES.extend(pages)   # from here on, every recorded fire can be named

    print(f"\n== fuzz: {rounds} mutations — the sibling's mutation, the sibling's truth")
    f = _gp.fuzz(pages, clean_kept, rounds)
    print(f"   mutations scored:                     {f['n']}")
    print(f"   the mutation really ate the article:  {f['real']}"
          f"   of those silent (parse=strict): {f['silent']}")
    print(f"\n   {'reading':<22} {'caught':>7} {'missed':>7} {'silent':>8} "
          f"{'no-cost':>8} {'partial':>8}")
    for k in _gp.CANDIDATES:
        s = f[k]
        print(f"   {k:<22} {s['caught']:>7} {s['missed_real']:>7} "
              f"{s['silent_caught']:>3}/{f['silent']:<4} {s['zero_cost']:>8} {s['partial']:>8}")

    print(f"\n== control: does this run reproduce what probe_gate_pos published?")
    ok = True
    for k, (caught, no_cost) in CONTROL.items():
        s = f[k]
        same = (s["caught"] == caught and s["zero_cost"] == no_cost)
        ok = ok and same
        print(f"   {k:<12} published {caught:>3} caught / {no_cost:>3} no-cost   "
              f"this run {s['caught']:>3} / {s['zero_cost']:>3}   "
              f"{'same' if same else 'DIFFERENT — this is another experiment'}")
    n = f["shipped_nodrop"]
    print(f"\n== the candidate, against the gate it would replace")
    s = f["shipped"]
    print(f"   shipped          caught {s['caught']:>3}  missed {s['missed_real']:>3}  "
          f"no-cost {s['zero_cost']:>3}  partial {s['partial']:>3}")
    print(f"   shipped, no CSS  caught {n['caught']:>3}  missed {n['missed_real']:>3}  "
          f"no-cost {n['zero_cost']:>3}  partial {n['partial']:>3}")
    print(f"   → fires removed by the exclusion: {s['zero_cost'] - n['zero_cost']} no-cost, "
          f"{s['partial'] - n['partial']} partial")
    print(f"   → real truncations it stops catching: {n['missed_real'] - s['missed_real']}"
          f"   {'(none — a strict improvement)' if n['missed_real'] <= s['missed_real'] else ''}")
    for ex in n["examples"]:
        print(f"   no-CSS MISSED: {ex['label']}  clean {ex['clean']:,} kept {ex['kept']:,} "
              f"(lost {ex['lost']:,})  ptext {ex['ptext']:,} li {ex['li']:,}  "
              f"eaten: {' '.join(f'{k}:{v}' for k, v in sorted(ex['kinds'].items(), key=lambda kv: -kv[1]))}")

    print(f"\n== the fires the exclusion takes away, named (not counted): {len(_removed)}")
    by_label: dict[str, int] = {}
    for r in _removed:
        by_label[r["label"]] = by_label.get(r["label"], 0) + 1
    print(f"   by page: " + "   ".join(f"{k} {v}" for k, v in
                                       sorted(by_label.items(), key=lambda kv: -kv[1])))
    for r in _removed[:8]:
        print(f"   {r['label']:<12} kept {r['kept']:,} (clean page kept {r['kept_nc']:,})  "
              f"in_root {r['in_root']:,} of which payload {r['payload']:,} → "
              f"nodrop {r['nodrop']:,}   scope {r['scope'][:32] or 'none'}   "
              f"page id by {r['lcp']} chars")
        print(f"       payload owned by: "
              + "   ".join(f"<{t}> {n:,}" for t, n in
                           sorted(r["payload_tags"].items(), key=lambda kv: -kv[1])))
        for chars, label, how, pay in r["frames"]:
            print(f"       {chars:>7}  {label:<28} ended {how:<8} of which payload {pay:,}")

    print(f"\n== left out ({len(skipped)}) — named, not folded into a total")
    for src, url, why in skipped:
        print(f"   {src:<12} {why:<40} {url}")


if __name__ == "__main__":
    main()
