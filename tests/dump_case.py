"""Replay probe_gate_pos's pinned fuzz and dump the mutated HTML of one case.

The twenty-fourth awakening could read `hn clean 2,513 kept 314 (lost 2,199)
eaten: -` and not say which page it was. Reproducing the exact mutation is what
turns a named case into a diagnosis: the rnd sequence depends only on `rounds`
and the page list, so replaying it with the same pinned order gives the same
mutations, character for character.

Usage:  python dump_case.py --fuzz 1500 --url readrare.com [--out DIR]
"""
import importlib.util
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, HERE)

import probe_gate_pos as pg  # noqa: E402
import probe_gate as _pg  # noqa: E402
import probe_rules as _pr  # noqa: E402
import keyhole  # noqa: E402


def main():
    rounds = int(sys.argv[sys.argv.index("--fuzz") + 1]) if "--fuzz" in sys.argv else 1500
    needle = sys.argv[sys.argv.index("--url") + 1] if "--url" in sys.argv else "readrare"
    outdir = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "."
    floor = keyhole.EMPTY_TEXT

    urls = _pg.read_list(pg.DEFAULT_LIST) + [(f"old-{n}", u) for n, u in
                                             [(s.replace(".", ""), u) for s, u in _pr.SITES]]
    rows = []
    for src, url in urls:
        if not _pg.is_html(url):
            continue
        try:
            html = _pg.cached_download(url)
        except Exception:
            continue
        c = pg.candidates(html)
        if c["kept"] < floor or not c["scope"]:
            continue
        rows.append({"src": src, "url": url, **c})
    rows.sort(key=lambda r: r["url"])          # --order=url
    print(f"{len(rows)} measurable pages, order pinned on the url")

    pages, clean_kept = [], []
    for r in rows:
        pages.append((_pg.cached_download(r["url"]), r["src"], r["url"]))
        clean_kept.append(pg.candidates(pages[-1][0])["kept"])

    rnd = random.Random(0)
    hits = 0
    for n in range(rounds):
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
        if needle not in url:
            continue
        try:
            c = pg.candidates(html)
        except Exception as e:
            print(f"round {n}: {url} raised {type(e).__name__}: {e}")
            continue
        lost = clean - c["kept"]
        real = lost > clean * 0.5 and lost > floor and c["kept"] > floor
        if not real:
            continue
        hits += 1
        name = os.path.join(outdir, f"case_{hits}_round{n}.html")
        with open(name, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(html)
        print(f"\nround {n}  {src}  {url}")
        print(f"  clean {clean:,}  kept {c['kept']:,}  lost {lost:,}  "
              f"no-chrome {c['kept_nc']:,}  rung {c['rung']}  scope {c['scope']!r}")
        print(f"  at offset {a:,}/{len(src):,}  rule {rule!r} x{cuts}")
        print(f"  inject at: ...{src[max(0, a - 60):a]!r} + >>>> + {src[a:a + 60]!r}...")
        print(f"  attributed: ptext {c['sup_ptext']:,} inline {c['sup_pinline']:,} "
              f"li {c['sup_li']:,} in_root {c['sup_in_root']:,} "
              f"open {c['sup_open']:,}  eaten {c['sup_kind']}")
        print(f"  fires: shipped {c['shipped_fires']} span {c['span_fires']} "
              f"ptext {c['ptext_fires']} punion {c['punion_fires']} "
              f"ppara {c['ppara_fires']} plist {c['plist_fires']} open {c['open_fires']}")
        print(f"  frames: {len(c['frames'])}")
        for f in c["frames"]:
            print(f"    {f['chars']:>8,}  {f['label']:<30} ended {f['how']:<8} {f['kinds']}")
        print(f"  wrote {name}")


if __name__ == "__main__":
    main()
